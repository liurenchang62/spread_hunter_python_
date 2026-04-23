"""
风控管理器。

两层检查：
  1. 同步快照检查（check_can_open）：使用缓存状态，在 tick 回调中同步执行，零等待
  2. 后台余额刷新（_balance_refresh_loop）：每 BALANCE_REFRESH_S 秒查一次各所余额

halt_type:
  "daily_loss"  — 日亏损超限：停止开仓、等待所有持仓平仓后退出进程
  "exposure"    — 敞口超限 / 失败冷却：暂停开仓，可自动恢复（余额或冷却恢复后继续）
  ""            — 正常
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from trader.config import (
    BALANCE_REFRESH_S,
    DAILY_HALT_PCT,
    FAILURE_COOLDOWN_S,
    MAX_CONSECUTIVE_FAILS,
    MAX_EXPOSURE_PCT,
    MAX_ORDERS_PER_MIN,
    REBALANCE_WARN_PCT,
)

logger = logging.getLogger("trader.risk")

# 各所余额查询 REST 接口（简化版：只查 USDT 可用余额）
# 需要 API key 已加载；key 由 exchange_client._load_keys 提供
_BALANCE_PATHS = {
    "binance": "/fapi/v2/balance",       # 需要签名
    "okx":     "/api/v5/account/balance?ccy=USDT",
    "gate":    "/api/v4/futures/usdt/accounts",
    "bitget":  "/api/v2/mix/account/accounts?productType=USDT-FUTURES",
}


@dataclass
class RiskState:
    day_start_total: float = 0.0          # 日初总余额（USDT）
    day_start_by_ex: dict = field(default_factory=dict)  # {exchange: balance}
    balance:         dict = field(default_factory=dict)  # 当前缓存余额
    total_exposure:  float = 0.0          # 当前敞口名义价值（两腿之和，USDT）
    consecutive_fails: int = 0
    cooldown_until:  float = 0.0          # monotonic 时间戳
    order_times:     dict = field(default_factory=dict)  # {exchange: deque[float]}
    halted:          bool = False
    halt_reason:     str  = ""
    halt_type:       str  = ""            # "daily_loss" | "exposure" | ""

    # 再平衡控制（由 RebalanceSupervisor 设置）
    rebalance_paused: bool = False        # True = 再平衡进行中，暂停开仓
    monitor_only:     bool = False        # True = 整体流动性不足，仅平仓不开仓


class RiskManager:
    """
    线程安全说明：所有方法均在 asyncio 事件循环的同一个线程中调用，无需加锁。
    """

    def __init__(self, clients: dict):
        """
        clients: {exchange: BaseClient}，用于查询余额。
        proxy 从每个 client.proxy 取得。
        """
        self._clients = clients
        self.state    = RiskState()
        self._stop    = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._balance_refresh_task: Optional[asyncio.Task] = None

    # ─── 启动 / 停止 ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动后台余额刷新任务，初始化日初状态。"""
        self._loop = asyncio.get_running_loop()
        await self._refresh_balances()
        self._init_day_start()
        self._balance_refresh_task = asyncio.ensure_future(self._balance_refresh_loop())
        logger.info(
            f"[risk] 启动 | 日初余额={self.state.day_start_total:.2f} USDT"
            f" | 各所={self.state.day_start_by_ex}"
        )

    def stop(self) -> None:
        self._stop.set()

    # ─── 同步快照检查（tick 回调中调用，必须极快）────────────────────────────

    def check_can_open(
        self,
        big: str,
        small: str,
        symbol: str,
        notional_usdt: float,
    ) -> tuple[bool, str]:
        """
        返回 (can_open: bool, reason: str)。
        仅读缓存状态，不做任何 I/O。
        """
        s = self.state

        # 是否已停机
        if s.halted:
            return False, f"halted({s.halt_type}): {s.halt_reason}"

        # 失败冷却
        now_mono = time.monotonic()
        if now_mono < s.cooldown_until:
            remaining = s.cooldown_until - now_mono
            return False, f"failure_cooldown({remaining:.0f}s)"

        # 日止损检查（每次开仓前用最新缓存余额估算）
        total_now = sum(s.balance.values()) if s.balance else s.day_start_total
        if s.day_start_total > 0 and total_now < s.day_start_total * DAILY_HALT_PCT:
            self._trigger_halt(
                "daily_loss",
                f"余额 {total_now:.2f} < 日初 {s.day_start_total:.2f} × {DAILY_HALT_PCT}",
            )
            return False, s.halt_reason

        # 敞口检查
        total_balance = total_now if total_now > 0 else s.day_start_total
        if total_balance > 0:
            new_exposure = s.total_exposure + notional_usdt
            if new_exposure > total_balance * MAX_EXPOSURE_PCT:
                return False, (
                    f"exposure {new_exposure:.2f} > "
                    f"limit {total_balance * MAX_EXPOSURE_PCT:.2f}"
                )

        # 下单频率（per-exchange）
        for ex in (big, small):
            if not self._check_order_rate(ex):
                return False, f"order_rate_limit({ex})"

        return True, ""

    # ─── 事件通知（交易执行后调用）──────────────────────────────────────────

    def on_order_placed(self, exchange: str) -> None:
        """下单成功后调用，记录时间戳用于频率限制。"""
        q = self.state.order_times.setdefault(exchange, deque())
        q.append(time.monotonic())

    def on_order_result(self, success: bool) -> None:
        """每次下单（两腿各一次，任一腿失败均调用 success=False）。"""
        if success:
            self.state.consecutive_fails = 0
        else:
            self.state.consecutive_fails += 1
            if self.state.consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                until = time.monotonic() + FAILURE_COOLDOWN_S
                self.state.cooldown_until = until
                logger.warning(
                    f"[risk] 连续失败 {self.state.consecutive_fails} 次，"
                    f"冷却 {FAILURE_COOLDOWN_S}s"
                )

    def on_position_opened(self, notional_usdt: float) -> None:
        self.state.total_exposure += notional_usdt

    def on_position_closed(self, notional_usdt: float, realized_pnl: float) -> None:
        self.state.total_exposure = max(0.0, self.state.total_exposure - notional_usdt)
        # 平仓后更新缓存余额（估算，避免等下次真实刷新）
        for ex in self.state.balance:
            pass  # 实际余额由后台循环刷新，此处不估算（避免双重修改）

    # ─── 日重置（UTC 午夜调用）───────────────────────────────────────────────

    def reset_daily(self) -> None:
        self._init_day_start()
        # 清除 daily_loss 类型的停机（exposure 类型不在此重置）
        if self.state.halt_type == "daily_loss":
            self.state.halted     = False
            self.state.halt_reason = ""
            self.state.halt_type   = ""
        logger.info(
            f"[risk] UTC 日重置 | 新日初余额={self.state.day_start_total:.2f} USDT"
        )

    # ─── 后台余额刷新 ────────────────────────────────────────────────────────

    async def _balance_refresh_loop(self) -> None:
        next_midnight = _next_utc_midnight()
        while not self._stop.is_set():
            await asyncio.sleep(BALANCE_REFRESH_S)
            await self._refresh_balances()
            self._check_rebalance_warning()

            # UTC 日切
            if time.time() >= next_midnight:
                self.reset_daily()
                next_midnight = _next_utc_midnight()

    async def _refresh_balances(self) -> None:
        """并发查询所有已配置交易所的 USDT 余额（委托给各 client.get_balance()）。"""
        tasks = {ex: asyncio.ensure_future(self._fetch_balance(ex))
                 for ex in self._clients}
        for ex, task in tasks.items():
            try:
                bal = await task
                if bal is not None:
                    self.state.balance[ex] = bal
            except Exception as e:
                logger.debug(f"[risk] {ex} 余额查询异常: {e}")

    async def _fetch_balance(self, exchange: str) -> Optional[float]:
        client = self._clients.get(exchange)
        if not client:
            return None
        try:
            bal = await client.get_balance()
            return bal
        except Exception as e:
            logger.debug(f"[risk] {exchange} 余额查询失败: {e}")
            return None

    # ─── 内部辅助 ─────────────────────────────────────────────────────────────

    def _init_day_start(self) -> None:
        self.state.day_start_total  = sum(self.state.balance.values()) if self.state.balance else 0.0
        self.state.day_start_by_ex  = dict(self.state.balance)

    def _check_rebalance_warning(self) -> None:
        for ex, start_bal in self.state.day_start_by_ex.items():
            cur = self.state.balance.get(ex)
            if cur is None or start_bal <= 0:
                continue
            drop = (start_bal - cur) / start_bal
            if drop >= REBALANCE_WARN_PCT:
                logger.warning(
                    f"[risk] {ex} 余额下降 {drop:.1%} "
                    f"({start_bal:.2f} → {cur:.2f} USDT)，建议补充保证金"
                )

    def _check_order_rate(self, exchange: str) -> bool:
        now = time.monotonic()
        q = self.state.order_times.get(exchange)
        if q is None:
            return True
        cutoff = now - 60.0
        while q and q[0] < cutoff:
            q.popleft()
        return len(q) < MAX_ORDERS_PER_MIN

    def _trigger_halt(self, halt_type: str, reason: str) -> None:
        if self.state.halted and self.state.halt_type == halt_type:
            return  # 已经处于该停机状态，不重复记录
        self.state.halted      = True
        self.state.halt_reason = reason
        self.state.halt_type   = halt_type
        logger.error(f"[risk] 触发停机 [{halt_type}]: {reason}")

    # ─── 诊断 ────────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        s = self.state
        return {
            "halted":          s.halted,
            "halt_type":       s.halt_type,
            "halt_reason":     s.halt_reason,
            "total_exposure":  s.total_exposure,
            "balance":         dict(s.balance),
            "day_start_total": s.day_start_total,
            "consecutive_fails": s.consecutive_fails,
            "cooldown_remaining": max(0.0, s.cooldown_until - time.monotonic()),
        }


def _next_utc_midnight() -> float:
    """返回下一个 UTC 午夜的 time.time() 时间戳。"""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # 加一天
    from datetime import timedelta
    midnight += timedelta(days=1)
    return midnight.timestamp()
