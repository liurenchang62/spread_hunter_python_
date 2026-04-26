"""
再平衡后台监控器（集成在主程序中）。

每隔 REBALANCE_CHECK_INTERVAL_H 小时自动执行：
  1. 再平衡检查 → 若触发：暂停 Trader 开仓 → 执行转账 → 等待到账 → 恢复
  2. 整体流动性检查 → 更新 Trader 的 monitor_only 标志（含迟滞）

与 Trader 通过 RiskState.rebalance_paused / monitor_only 两个标志通信，
所有操作在同一个 asyncio 事件循环中，无需跨线程锁。
"""

import asyncio
import logging
import time
from typing import Optional

from trader.config import (
    REBALANCE_CHECK_INTERVAL_H,
    REBALANCE_CONFIRM_TIMEOUT_S,
    REBALANCE_FLOOR_PCT,
    CASH_RATIO_MIN,
    CASH_RATIO_RESUME,
)
from rebalance._common import (
    load_live_clients, close_all,
    fetch_all_states, fetch_all_fees,
    check_rebalance, check_liquidity,
    plan_transfers, Transfer,
    ExchangeState,
)

logger = logging.getLogger("rebalance.supervisor")


class RebalanceSupervisor:
    """
    后台再平衡监控器。

    用法（在 main.py 的 asyncio.gather 中）：
        supervisor = RebalanceSupervisor(trader.risk)
        await asyncio.gather(tracker.start(), trader.start(), supervisor.start())
    """

    def __init__(self, risk_state_holder):
        """
        risk_state_holder: RiskManager 实例（持有 .state）。
        supervisor 通过修改 risk_state_holder.state 来控制 Trader 行为。
        """
        self._risk  = risk_state_holder
        self._stop  = asyncio.Event()
        self._clients: Optional[dict] = None

    # ─── 公共接口 ─────────────────────────────────────────────────────────────

    async def start(self):
        """启动后台监控循环（每 CHECK_INTERVAL_H 小时检查一次）。"""
        logger.info(
            f"[supervisor] 启动，检查周期={REBALANCE_CHECK_INTERVAL_H}h，"
            f"再平衡下限={REBALANCE_FLOOR_PCT*100:.0f}%，"
            f"流动性下限={CASH_RATIO_MIN*100:.0f}%"
        )
        # 启动时立即检查一次
        await self._run_checks()

        while not self._stop.is_set():
            # 等待下一个检查周期（可被 stop() 中断）
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=REBALANCE_CHECK_INTERVAL_H * 3600,
                )
            except asyncio.TimeoutError:
                pass   # 正常超时，执行检查

            if not self._stop.is_set():
                await self._run_checks()

        logger.info("[supervisor] 已停止")

    def stop(self):
        self._stop.set()

    # ─── 核心检查流程 ─────────────────────────────────────────────────────────

    async def _run_checks(self):
        logger.info("[supervisor] 开始定时检查…")
        try:
            clients = load_live_clients()
        except SystemExit:
            logger.error("[supervisor] 无法加载实盘 API Key，跳过本次检查")
            return

        try:
            states = await fetch_all_states(clients)

            # ── Step 1: 再平衡检查 ──────────────────────────────────────────
            await self._check_rebalance(clients, states)

            # ── Step 2: 整体流动性检查 ──────────────────────────────────────
            # 再平衡可能改变了现金分布，但总量不变，流动性比不变
            # 仍使用原始 states（避免多余 API 调用）
            self._check_liquidity(states)

        except Exception as e:
            logger.error(f"[supervisor] 检查异常: {e}", exc_info=True)
        finally:
            await close_all(clients)

    async def _check_rebalance(self, clients: dict, states: dict[str, ExchangeState]):
        rc = check_rebalance(states)

        n    = len(states)
        total_cash = rc.total_cash
        floor_cash = rc.floor_cash

        logger.info(
            f"[supervisor] 再平衡检查: 总现金={total_cash:.2f}U  "
            f"均值={rc.target_cash:.2f}U  下限={floor_cash:.2f}U"
            f"  sinks={rc.sinks}"
        )

        if not rc.should_rebalance:
            logger.info(f"[supervisor] 无需再平衡: {rc.reason}")
            return

        logger.warning(
            f"[supervisor] 触发再平衡！低于下限({REBALANCE_FLOOR_PCT*100:.0f}%)的交易所: {rc.sinks}"
        )

        # ── 暂停 Trader 开仓 ────────────────────────────────────────────────
        self._set_rebalance_paused(True)
        logger.info("[supervisor] Trader 开仓已暂停")

        all_arrived = False
        try:
            all_fees = await fetch_all_fees(clients)
            transfers = plan_transfers(rc, states, all_fees)

            if not transfers:
                logger.error("[supervisor] 无法规划转账路径，取消再平衡")
                return

            for t in transfers:
                logger.info(
                    f"[supervisor] 计划转账: {t.source}→{t.target} "
                    f"{t.amount:.2f}U via {t.path.label}"
                )

            # ── 执行转账（含等待全部到账）──────────────────────────────────
            all_arrived = await self._execute_transfers(clients, transfers, states)

        except Exception as e:
            logger.error(f"[supervisor] 再平衡执行异常: {e}", exc_info=True)
        finally:
            # 无论成功与否，必须恢复开仓（不能永久暂停）
            self._set_rebalance_paused(False)
            if all_arrived:
                logger.info("[supervisor] 所有转账已确认到账，Trader 开仓已恢复")
            else:
                logger.warning(
                    "[supervisor] 部分转账未在超时内确认到账，已强制恢复开仓，请手动检查余额"
                )

    def _check_liquidity(self, states: dict[str, ExchangeState]):
        currently_monitor_only = self._risk.state.monitor_only
        lc = check_liquidity(states, currently_monitor_only)

        logger.info(
            f"[supervisor] 流动性检查: cash_ratio={lc.cash_ratio*100:.1f}%  "
            f"({lc.total_cash:.2f}U/{lc.total_equity:.2f}U)  "
            f"monitor_only={lc.monitor_only}"
        )

        if lc.monitor_only != currently_monitor_only:
            if lc.monitor_only:
                logger.warning(
                    f"[supervisor] 整体流动性不足（{lc.cash_ratio*100:.1f}% "
                    f"< {CASH_RATIO_MIN*100:.0f}%）→ 进入仅监控模式，停止开仓"
                )
            else:
                logger.info(
                    f"[supervisor] 流动性已恢复（{lc.cash_ratio*100:.1f}% "
                    f"> {CASH_RATIO_RESUME*100:.0f}%）→ 退出仅监控模式"
                )
            self._risk.state.monitor_only = lc.monitor_only

    # ─── 转账执行 ─────────────────────────────────────────────────────────────

    async def _execute_transfers(
        self,
        clients: dict,
        transfers: list[Transfer],
        states: dict[str, ExchangeState],
    ) -> bool:
        """
        执行所有转账并等待全部到账。
        返回 True = 所有转账均已确认到账；False = 有超时未确认。
        """
        from collections import defaultdict
        by_source: dict[str, list[Transfer]] = defaultdict(list)
        for t in transfers:
            by_source[t.source].append(t)

        # ── Step 1: 合约 → 现货划转（各来源所）──────────────────────────────
        for src, src_transfers in by_source.items():
            total_out     = sum(t.amount for t in src_transfers)
            spot_now      = states[src].spot
            futures_avail = states[src].available
            need_transfer = max(0.0, total_out - spot_now)

            if need_transfer > 0:
                if need_transfer > futures_avail:
                    logger.error(
                        f"[supervisor] {src}: 合约可用余额不足"
                        f"（需{need_transfer:.2f}U，仅{futures_avail:.2f}U）"
                    )
                    return False
                ok = await clients[src].transfer_to_spot(need_transfer)
                if ok:
                    logger.info(f"[supervisor] {src} 合约→现货划转 {need_transfer:.2f}U 成功")
                else:
                    logger.error(f"[supervisor] {src} 划转失败，终止再平衡")
                    return False

        # ── Step 2: 提现 + 等待到账 ──────────────────────────────────────────
        all_arrived = True
        for t in transfers:
            p = t.path
            result = await clients[t.source].withdraw(p.network, p.address, t.amount)
            if not result["success"]:
                logger.error(
                    f"[supervisor] 提现失败: {t.source}→{t.path.dst} "
                    f"err={result['error']}"
                )
                all_arrived = False
                await asyncio.sleep(1.5)
                continue

            logger.info(
                f"[supervisor] 提现成功: {t.source}→{p.dst} "
                f"{t.amount:.2f}U via {p.network}  orderId={result['id']}"
            )

            # 等待最终目标到账
            # 中转路径需两跳，timeout 加倍；同时打印人工操作提示
            if p.kind == "hub":
                logger.warning(
                    f"[supervisor] 中转路径：资金已发往 {p.dst}，"
                    f"需手动完成第2步（{p.dst}→{t.target} via {p.hub_network}），"
                    f"将等待最终到账（超时={REBALANCE_CONFIRM_TIMEOUT_S*2}s）"
                )
                timeout = REBALANCE_CONFIRM_TIMEOUT_S * 2
            else:
                timeout = REBALANCE_CONFIRM_TIMEOUT_S

            arrived = await self._poll_deposit(clients, t.target, timeout)
            if arrived:
                logger.info(f"[supervisor] {t.target} 到账已确认")
            else:
                logger.warning(
                    f"[supervisor] {t.target} 到账超时（{timeout}s），"
                    f"资金可能仍在传输，请手动确认"
                )
                all_arrived = False

            await asyncio.sleep(1.5)

        return all_arrived

    async def _poll_deposit(
        self, clients: dict, exchange: str, timeout_s: float
    ) -> bool:
        try:
            before = await clients[exchange].get_spot_balance()
        except Exception:
            before = 0.0

        elapsed  = 0.0
        interval = min(30.0, timeout_s / 10)

        while elapsed < timeout_s:
            await asyncio.sleep(interval)
            elapsed += interval
            try:
                after = await clients[exchange].get_spot_balance()
                if after > before + 0.5:
                    logger.info(
                        f"[supervisor] {exchange} 到账确认: "
                        f"{before:.2f}→{after:.2f}U"
                    )
                    return True
            except Exception:
                pass
            logger.debug(f"[supervisor] {exchange} 等待到账 {elapsed:.0f}s/{timeout_s:.0f}s")

        return False

    # ─── 状态操作 ─────────────────────────────────────────────────────────────

    def _set_rebalance_paused(self, paused: bool):
        self._risk.state.rebalance_paused = paused
