"""
Trader：消费 tracker 的信号，执行开/平仓。

架构（latest-wins，最低延迟）：
  - tracker 调用 _on_opportunity(sig) 同步回调（in-flow，与 tick 处理同步）
      cost_evaluate() + risk.check_can_open() 在此同步完成（纯内存操作）
      通过 create_task 将实际 HTTP 下单调度到事件循环
      latest-wins：同一 (big, small, sym) 的旧任务若未开始 HTTP 则取消
  - tracker 调用 _on_tick(tick) 同步回调（in-flow exit 检查）
      只做内存读写，触发 _do_exit task
  - _timeout_loop：1s 定时器检查超时持仓
  - _market_info_refresh_loop：每 MARKET_INFO_REFRESH_H 小时刷新市场信息
  - risk._balance_refresh_loop：由 RiskManager 内部后台运行

daily_loss 停机流程：
  risk 触发 daily_loss → _on_opportunity 不再开仓 →
  等待所有持仓平仓（_on_tick / _timeout_loop 正常平仓）→
  Trader.start() 返回，由调用方决定是否退出进程

LIVE_TRADING_ON = False 时仅使用测试网/Demo 环境。
"""

import asyncio
import logging
import sys
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from clients import to_exchange_fmt
from tracker.models import MarketEvent, Tick
import trader.config as _trader_cfg
from trader.config import (
    TAKE_PROFIT_PCT,
    MAX_HOLD_SECONDS,
    MIN_ANOMALY_TO_OPEN_PCT,
    PAIR_CAPITAL_PCT,
    PAIR_CAPITAL_FALLBACK_USDT,
    MIN_ORDER_NOTIONAL_USDT,
    STOP_LOSS_PCT,
    TESTNET_EXCHANGES,
    MARKET_INFO_REFRESH_H,
    FUNDING_EXIT_BEFORE_S,
)

MAX_SYMBOL_NOTIONAL_PCT = getattr(_trader_cfg, "MAX_SYMBOL_NOTIONAL_PCT", 0.0)

# 与旧版仅复制 config.example 的部署兼容（未定义时使用安全默认）
LEVERAGE = getattr(_trader_cfg, "LEVERAGE", 1)
SESSION_MAX_ENTRIES = getattr(_trader_cfg, "SESSION_MAX_ENTRIES", None)
from trader import feishu_push
from trader.cost_model import evaluate as cost_evaluate
from trader.exchange_client import build_clients, OrderResult
from trader.market_info import MarketInfo, refresh_market_info
from trader.position import Leg, Position
from trader.position_manager import PositionManager
from trader.risk import RiskManager
from trader.orderbook import OrderBookCache

logger = logging.getLogger("trader")


class Trader:
    """
    与 Tracker 协同工作。

    启动方式：
        tracker = Tracker()
        trader  = Trader(tracker)
        await asyncio.gather(tracker.start(), trader.start())
    """

    def __init__(self, tracker, proxy: str = ""):
        self.tracker = tracker
        self._active = tracker.active_positions

        self._proxy  = proxy or ""
        self.pm      = PositionManager(self._active)
        self.clients = build_clients(live=_trader_cfg.LIVE_TRADING_ON, proxy=self._proxy)
        self.mi      = MarketInfo()
        self.risk    = RiskManager(self.clients)
        self.ob      = OrderBookCache(proxy=self._proxy)

        # latest-wins 开仓任务表：key=(big,small,sym), value=asyncio.Task
        # 每次新信号到来时，若旧任务尚未完成则取消（避免处理陈旧信号）
        self._entry_tasks: dict[tuple, asyncio.Task] = {}

        # 平仓任务表（防止同一仓位被重复平仓）
        self._exit_tasks: dict[str, asyncio.Task] = {}   # pos_id → Task

        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = asyncio.Event()


        # 统计
        self._n_opened  = 0
        self._n_closed  = 0
        self._total_pnl = 0.0

        # 会话开仓上限（SESSION_MAX_ENTRIES）
        self._session_cap_reached = False   # 累计开仓已达上限，不再接受新开仓

        mode = "主网实盘" if _trader_cfg.LIVE_TRADING_ON else "测试网/Demo"
        logger.info(f"[trader] 初始化 | 模式={mode} | 客户端={list(self.clients.keys())}")

    # ─── 主入口 ───────────────────────────────────────────────────────────────

    async def start(self):
        self._loop = asyncio.get_running_loop()

        # 注册同步回调（in-flow，最低延迟）
        self.tracker.register_opportunity_callback(self._on_opportunity)
        self.tracker.register_tick_callback(self._on_tick)
        self.tracker.register_reconnect_callback(self._on_reconnect)

        # 初始拉取市场信息
        has_symbol_sel = hasattr(self.tracker, "symbol_sel")
        logger.info(f"[trader] 检查 symbol_sel: {has_symbol_sel}")
        symbols = set(self.tracker.symbol_sel.symbols) if has_symbol_sel else set()
        logger.info(f"[trader] 初始标的数量: {len(symbols)}")
        if symbols:
            await refresh_market_info(self.mi, symbols, proxy=self._proxy, live=_trader_cfg.LIVE_TRADING_ON)
            logger.info(f"[trader] 市场信息已刷新，symbol_info 数量: {len(self.mi.symbol_info)}")
            # 检查几个关键标的的 step size
            for sym in ['PIEVERSEUSDT', 'RAVEUSDT']:
                info = self.mi.symbol_info.get(('binance', sym))
                if info:
                    logger.info(f"[trader] Binance {sym}: qty_step={info.qty_step}, min_qty={info.min_qty}")

        # 启动风控后台（余额查询 + 日重置）
        await self.risk.start()

        logger.info("[trader] 开始处理信号…")
        await feishu_push.push_text_async(
            feishu_push.format_trading_started(tuple(sorted(self.clients.keys()))),
            live=_trader_cfg.LIVE_TRADING_ON,
        )
        try:
            await asyncio.gather(
                self._timeout_loop(),
                self._position_sweep_loop(),
                self._market_info_refresh_loop(symbols),
                self._daily_halt_monitor(),
            )
        finally:
            if self.risk._balance_refresh_task:
                self.risk._balance_refresh_task.cancel()
            await self._close_all_clients()
            logger.info(
                f"[trader] 退出 | 累计开仓={self._n_opened} 平仓={self._n_closed}"
                f" 总PnL={self._total_pnl:+.4f} USDT"
            )

    def stop(self):
        self._stop.set()
        self.risk.stop()

    # ─── Opportunity 回调（同步，in-flow，最低延迟）──────────────────────────

    def _on_opportunity(self, sig: MarketEvent):
        """
        tracker 每产生一个 opportunity 信号就同步调用此方法。

        同步部分（纯内存，μs 级）：
          1. 基本过滤（交易所/最小异常）
          2. 仓位限制检查
          3. risk.check_can_open（纯内存缓存，无 I/O）

        若通过：取消同一 key 的旧任务 → 创建新任务（HTTP I/O 在异步任务中执行）
        成本模型（含订单薄滑点）仅在 _place_entry 中执行一次。
        """
        if self._loop is None:
            return

        # 再平衡暂停 → 禁止开仓（平仓不受影响）
        if self.risk.state.rebalance_paused:
            logger.info("[trader] 再平衡进行中，暂停开仓")
            return

        # 会话开仓上限检查
        if self._session_cap_reached:
            return
        if SESSION_MAX_ENTRIES is not None and self._n_opened >= SESSION_MAX_ENTRIES:
            self._session_cap_reached = True
            logger.warning(
                f"[trader] 会话开仓上限 {SESSION_MAX_ENTRIES} 已达到，停止新开仓；"
                f"等待现有持仓平仓后进入纯监控模式"
            )
            return

        big, small, sym = sig.big_exchange, sig.small_exchange, sig.symbol

        # 交易所过滤
        if not _trader_cfg.LIVE_TRADING_ON:
            if big not in TESTNET_EXCHANGES or small not in TESTNET_EXCHANGES:
                logger.info(f"[trader] 拒绝 {sym} {big}/{small} | 交易所不在测试网支持列表")
                return
        if big not in self.clients or small not in self.clients:
            logger.info(f"[trader] 拒绝 {sym} {big}/{small} | API客户端未初始化")
            return

        # 基本信号过滤
        if abs(sig.anomaly_pct) < MIN_ANOMALY_TO_OPEN_PCT:
            logger.info(f"[trader] 拒绝 {sym} {big}/{small} | anomaly={sig.anomaly_pct:.3f}% < 门槛{MIN_ANOMALY_TO_OPEN_PCT}%")
            return

        # 仓位限制
        can_open, position_reason = self.pm.can_open_with_reason(big, small, sym)
        if not can_open:
            logger.info(f"[trader] 拒绝 {sym} {big}/{small} | 仓位限制: {position_reason}")
            return

        # 单标的名义价值集中度检查
        if MAX_SYMBOL_NOTIONAL_PCT > 0:
            total_eq = sum(self.risk.state.balance.values())
            if total_eq > 0:
                sym_notional = sum(
                    (p.small_leg.size_usdt if p.small_leg else 0.0)
                    + (p.big_leg.size_usdt  if p.big_leg  else 0.0)
                    for p in self.pm.open_positions()
                    if p.symbol == sym and p.is_open
                )
                max_notional = total_eq * MAX_SYMBOL_NOTIONAL_PCT
                if sym_notional >= max_notional:
                    logger.info(
                        f"[trader] 拒绝 {sym} {big}/{small} | 单标的仓位"
                        f" {sym_notional:.1f}U >= 上限 {max_notional:.1f}U ({MAX_SYMBOL_NOTIONAL_PCT:.0%})"
                    )
                    return

        # 动态单腿资金 = min(各所余额) × 1% / 2 = 0.5%，但不少于最小下单金额
        balances = self.risk.state.balance
        if balances:
            leg_budget = min(balances.values()) * PAIR_CAPITAL_PCT / 2.0
        else:
            leg_budget = PAIR_CAPITAL_FALLBACK_USDT / 2.0
        
        # 确保单腿资金不低于最小名义价值要求（两腿必须一致）
        leg_budget = max(leg_budget, MIN_ORDER_NOTIONAL_USDT)

        # 风控检查（同步，纯内存缓存）：单腿预算 vs 各所可用余额
        ok, reason = self.risk.check_can_open(big, small, sym, leg_budget)
        if not ok:
            logger.info(f"[trader] 拒绝 {sym} {big}/{small} | 风控: {reason}")
            return

        # latest-wins：取消同 key 的旧任务
        key = (big, small, sym)
        old_task = self._entry_tasks.get(key)
        if old_task and not old_task.done():
            old_task.cancel()

        # 调度新任务（HTTP 下单在事件循环中异步执行）
        task = self._loop.create_task(self._place_entry(sig))
        self._entry_tasks[key] = task
        task.add_done_callback(lambda t: self._entry_tasks.pop(key, None))

    # ─── Tick 回调（同步，in-flow exit 检查）─────────────────────────────────

    def _on_tick(self, tick: Tick):
        if self._loop is None:
            return
        sym = tick.symbol
        for pos in self.pm.open_positions():
            if pos.symbol != sym or pos.status != "open":
                continue
            # 已有平仓任务时跳过（避免重复下单）
            if pos.id in self._exit_tasks and not self._exit_tasks[pos.id].done():
                continue

            big, small = pos.big_exchange, pos.small_exchange
            latest   = self.tracker.latest.get(sym, {})
            big_tick = latest.get(big)
            sml_tick = latest.get(small)
            if not big_tick or not sml_tick:
                continue

            pnl_pct = self._compute_pnl_pct(pos, sml_tick.mid, big_tick.mid)
            reason = self._check_exit_reason(pos, pnl_pct)
            if reason:
                self._schedule_exit(pos, pnl_pct, reason)

    # ─── WS 重连回调（同步）──────────────────────────────────────────────────

    def _on_reconnect(self, exchange: str):
        """
        某所 WS 重连时同步调用。
        立即对涉及该交易所的所有开放持仓做一次 exit 检查，
        补偿断线期间可能错过的 tick 信号。
        """
        if self._loop is None:
            return
        for pos in self.pm.open_positions():
            if pos.status != "open":
                continue
            if pos.big_exchange != exchange and pos.small_exchange != exchange:
                continue
            if pos.id in self._exit_tasks and not self._exit_tasks[pos.id].done():
                continue
            sym = pos.symbol
            big, small = pos.big_exchange, pos.small_exchange
            latest   = self.tracker.latest.get(sym, {})
            big_tick = latest.get(big)
            sml_tick = latest.get(small)
            if not big_tick or not sml_tick:
                continue
            pnl_pct = self._compute_pnl_pct(pos, sml_tick.mid, big_tick.mid)
            reason = self._check_exit_reason(pos, pnl_pct)
            if reason:
                self._schedule_exit(pos, pnl_pct, reason)
                logger.info(f"[trader] 重连后检测到 {pos.id} 满足 {reason}，触发平仓")

    # ─── 开仓执行（async，HTTP I/O）─────────────────────────────────────────

    async def _place_entry(self, ev: MarketEvent):
        big, small, sym = ev.big_exchange, ev.small_exchange, ev.symbol

        # 二次检查（任务排队期间状态可能变化）
        if not self.pm.can_open(big, small, sym):
            return

        # 拉取主网真实订单薄（唯一一次滑点评估）
        ob_pair = await self.ob.get_pair(small, sym, big, sym)
        balances = self.risk.state.balance
        leg_budget = (min(balances.values()) * PAIR_CAPITAL_PCT / 2.0
                      if balances else PAIR_CAPITAL_FALLBACK_USDT / 2.0)
        # 确保单腿资金不低于最小名义价值要求（两腿必须一致）
        leg_budget = max(leg_budget, MIN_ORDER_NOTIONAL_USDT)
        cr = cost_evaluate(ev, big, small, self.mi,
                           leg_budget=leg_budget,
                           small_ob=ob_pair.small,
                           big_ob=ob_pair.big)
        if not cr.should_trade:
            logger.debug(f"[trader] 成本模型拒绝 | {sym} {big}/{small} | {cr.reason}")
            return

        # 二次风控检查（此时 target_qty 已精确计算）
        ok, reason = self.risk.check_can_open(
            big, small, sym, cr.target_qty * ev.small_mid * 2
        )
        if not ok:
            return

        logger.info(
            f"[trader] ENTRY | {sym} {big}/{small} dir={ev.direction}"
            f" anomaly={ev.anomaly_pct:+.3f}%"
            f" qty={cr.target_qty:.6f} est_net={cr.net_profit_usdt:+.4f}USDT"
            f" roi={cr.net_roi:.4f}"
        )

        small_side = "buy"  if ev.direction == "long" else "sell"
        big_side   = "sell" if ev.direction == "long" else "buy"
        small_sym  = to_exchange_fmt(sym, small)
        big_sym    = to_exchange_fmt(sym, big)

        # 设置杠杆（并发，失败只记日志不阻断）
        await asyncio.gather(
            self.clients[small].set_leverage(small_sym, LEVERAGE),
            self.clients[big].set_leverage(big_sym, LEVERAGE),
            return_exceptions=True,
        )

        # 并发下两腿
        small_task = self.clients[small].place_order(
            symbol=small_sym, side=small_side,
            target_qty=cr.target_qty,
            ref_price=ev.small_ask if small_side == "buy" else ev.small_bid,
            symbol_info=self.mi.get_symbol_info(small, sym),
        )
        big_task = self.clients[big].place_order(
            symbol=big_sym, side=big_side,
            target_qty=cr.target_qty,
            ref_price=ev.big_bid if big_side == "sell" else ev.big_ask,
            symbol_info=self.mi.get_symbol_info(big, sym),
        )
        small_res, big_res = await asyncio.gather(small_task, big_task)

        # 通知风控
        self.risk.on_order_placed(small)
        self.risk.on_order_placed(big)
        self.risk.on_order_result(small_res.success)
        self.risk.on_order_result(big_res.success)

        if not small_res.success or not big_res.success:
            # 检查是否为合约不支持（小所不支持该币种）
            small_unsupported = small_res.error and ("CONTRACT_NOT_FOUND" in str(small_res.error) or "not found" in str(small_res.error).lower())
            big_unsupported = big_res.error and ("not found" in str(big_res.error).lower() or "invalid symbol" in str(big_res.error).lower())
            
            if small_unsupported or big_unsupported:
                logger.warning(
                    f"[trader] 开仓失败 {sym} {big}/{small} | 合约不支持 | "
                    f"small_err={small_res.error} big_err={big_res.error} | "
                    f"建议：从监控列表中移除 {sym} 或检查交易所是否上线该币种"
                )
            else:
                logger.warning(
                    f"[trader] 开仓失败 {sym} {big}/{small} | "
                    f"small_ok={small_res.success} big_ok={big_res.success} | "
                    f"small_err={small_res.error} big_err={big_res.error}"
                )
            await self._emergency_close(ev, small_res, big_res, small_sym, big_sym, small_side, big_side)
            return

        small_leg = Leg(
            exchange=small, symbol=small_sym, side=small_side,
            order_id=small_res.order_id, entry_price=small_res.fill_price,
            size_usdt=small_res.fill_size * small_res.fill_price,
            size_base=small_res.fill_size, fee_usdt=small_res.fee_usdt,
        )
        big_leg = Leg(
            exchange=big, symbol=big_sym, side=big_side,
            order_id=big_res.order_id, entry_price=big_res.fill_price,
            size_usdt=big_res.fill_size * big_res.fill_price,
            size_base=big_res.fill_size, fee_usdt=big_res.fee_usdt,
        )
        pos = Position(
            symbol=sym, big_exchange=big, small_exchange=small,
            direction=ev.direction, small_leg=small_leg, big_leg=big_leg,
            open_anomaly_pct=ev.anomaly_pct,
        )
        self.pm.add_position(pos)
        self._n_opened += 1

        notional = (small_res.fill_size * small_res.fill_price
                    + big_res.fill_size * big_res.fill_price)
        self.risk.on_position_opened(notional)

        # 开仓后立即解冻基准，避免异常价格污染滚动中位数
        self.tracker.baseline.unfreeze_pair(big, small, sym)

        logger.info(
            f"[trader] 开仓成功 {pos.id} | small@{small_res.fill_price:.4f}"
            f" big@{big_res.fill_price:.4f}"
        )
        await feishu_push.push_text_async(
            feishu_push.format_open_position(pos, ev.anomaly_pct),
            live=_trader_cfg.LIVE_TRADING_ON,
        )

    # ─── 平仓执行 ─────────────────────────────────────────────────────────────

    async def _do_exit(self, pos: Position, pnl_pct: float, reason: str):
        # 允许 "closing"：前一次平仓任务在 mark_closing 之后异常终止时，重试需要能继续
        if pos.status not in ("open", "closing"):
            return

        logger.info(
            f"[trader] EXIT | {pos.id} {pos.symbol} reason={reason}"
            f" pnl={pnl_pct:+.3f}% hold={pos.hold_seconds:.1f}s"
        )
        self.pm.mark_closing(pos.id)

        small_close_side = "sell" if pos.small_leg.side == "buy" else "buy"
        big_close_side   = "sell" if pos.big_leg.side   == "buy" else "buy"

        ref_small = self.tracker.latest.get(pos.symbol, {}).get(pos.small_exchange)
        ref_big   = self.tracker.latest.get(pos.symbol, {}).get(pos.big_exchange)
        p_small   = ref_small.mid if ref_small else pos.small_leg.entry_price
        p_big     = ref_big.mid   if ref_big   else pos.big_leg.entry_price

        small_task = self.clients[pos.small_exchange].place_order(
            symbol=pos.small_leg.symbol, side=small_close_side,
            target_qty=pos.small_leg.size_base, ref_price=p_small,
            symbol_info=self.mi.get_symbol_info(pos.small_exchange, pos.symbol),
            reduce_only=True,
        )
        big_task = self.clients[pos.big_exchange].place_order(
            symbol=pos.big_leg.symbol, side=big_close_side,
            target_qty=pos.big_leg.size_base, ref_price=p_big,
            symbol_info=self.mi.get_symbol_info(pos.big_exchange, pos.symbol),
            reduce_only=True,
        )
        small_res, big_res = await asyncio.gather(small_task, big_task)

        self.risk.on_order_placed(pos.small_exchange)
        self.risk.on_order_placed(pos.big_exchange)
        self.risk.on_order_result(small_res.success)
        self.risk.on_order_result(big_res.success)

        if not small_res.success and not big_res.success:
            # 双腿均失败：保留 closing 状态，由 _timeout_loop / _position_sweep_loop 重试
            logger.warning(
                f"[trader] 平仓双腿失败 {pos.id} | 保留closing待重试"
                f" | small_err={small_res.error} | big_err={big_res.error}"
            )
            return

        if not small_res.success or not big_res.success:
            # 单腿失败：一腿已成交，另一腿失败 → 不可安全重试（会双向平仓）
            # 记录 CRITICAL 要求人工介入，然后关闭 PM 追踪（防止无限重试）
            failed_ex  = pos.small_exchange if not small_res.success else pos.big_exchange
            failed_err = small_res.error    if not small_res.success else big_res.error
            logger.critical(
                f"[trader] ⚠️ 平仓单腿失败 {pos.id} | 交易所={failed_ex}"
                f" err={failed_err} | 请手动检查该所是否有残留敞口！"
            )
            await feishu_push.push_text_async(
                feishu_push.format_close_leg_failed(pos, failed_ex, str(failed_err)),
                live=_trader_cfg.LIVE_TRADING_ON,
            )
            # 继续执行 close_position（从追踪中移除，防止重试使问题恶化）

        notional = pos.small_leg.size_usdt + pos.big_leg.size_usdt
        closed = self.pm.close_position(
            pos_id=pos.id, close_pnl_pct=pnl_pct, reason=reason,
            small_close_result=small_res, big_close_result=big_res,
        )
        if closed:
            self._n_closed  += 1
            self._total_pnl += closed.pnl_usdt
            self.risk.on_position_closed(notional, closed.pnl_usdt)
            logger.info(
                f"[trader] 平仓完成 {pos.id} | pnl={closed.pnl_usdt:+.4f} USDT"
                f" | 累计PnL={self._total_pnl:+.4f} USDT"
            )
            await feishu_push.push_text_async(
                feishu_push.format_close_position(closed, self._total_pnl),
                live=_trader_cfg.LIVE_TRADING_ON,
            )
            # 止损触发 → 当天不再开新仓
            if reason == "stop_loss":
                self.risk.state.stop_loss_today = True
                logger.warning("[trader] 止损平仓，当日停止开仓（UTC 午夜重置）")
            # 会话上限已达且所有持仓已清空 → 纯监控模式
            if self._session_cap_reached and not self.pm.open_positions():
                logger.warning(
                    f"[trader] 会话开仓上限 {SESSION_MAX_ENTRIES} 笔已全部平仓，"
                    f"进入纯监控模式（本次启动不再开仓）"
                )

    # ─── 超时检查（1s timer）────────────────────────────────────────────────

    async def _timeout_loop(self):
        while not self._stop.is_set():
            await asyncio.sleep(1.0)
            for pos in self.pm.open_positions():
                if pos.id in self._exit_tasks and not self._exit_tasks[pos.id].done():
                    continue
                if pos.hold_seconds >= MAX_HOLD_SECONDS:
                    self._schedule_exit(pos, 0.0, "timeout")

    # ─── 持仓周期性扫描（WS 断线兜底）──────────────────────────────────────

    async def _position_sweep_loop(self):
        """
        每 5 秒独立扫描所有开放持仓，用 tracker.latest 中缓存的最新价格
        重新计算 exit 条件。
        与 _on_tick（实时）和 _timeout_loop（超时）互补：
        保证 WS 断线期间只要有任何一所还在推 tick，持仓仍能正常退出。
        """
        while not self._stop.is_set():
            await asyncio.sleep(5.0)
            for pos in self.pm.open_positions():
                if pos.id in self._exit_tasks and not self._exit_tasks[pos.id].done():
                    continue
                sym = pos.symbol
                big, small = pos.big_exchange, pos.small_exchange
                latest   = self.tracker.latest.get(sym, {})
                big_tick = latest.get(big)
                sml_tick = latest.get(small)
                if not big_tick or not sml_tick:
                    continue
                pnl_pct = self._compute_pnl_pct(pos, sml_tick.mid, big_tick.mid)
                reason = self._check_exit_reason(pos, pnl_pct)
                if reason:
                    self._schedule_exit(pos, pnl_pct, reason)

    # ─── 日止损监控 ────────────────────────────────────────────────────────

    async def _daily_halt_monitor(self):
        """
        检测 daily_loss 停机：等待所有持仓平仓后，退出 trader 主循环。
        """
        while not self._stop.is_set():
            await asyncio.sleep(2.0)
            rs = self.risk.state
            if rs.halted and rs.halt_type == "daily_loss":
                logger.error(
                    f"[trader] 日止损触发，等待持仓全部平仓后退出… | {rs.halt_reason}"
                )
                # 等待所有持仓平仓
                deadline = time.monotonic() + 300  # 最多等 5 分钟让持仓平完
                while time.monotonic() < deadline:
                    if not self.pm.open_positions():
                        break
                    await asyncio.sleep(1.0)
                logger.error("[trader] 日止损停机，退出 trader")
                self._stop.set()
                return

    # ─── 市场信息定期刷新 ────────────────────────────────────────────────────

    async def _market_info_refresh_loop(self, symbols: set):
        # 初始刷新：等待 symbols 可用后立即刷新
        while not self._stop.is_set():
            if hasattr(self.tracker, "symbol_sel"):
                symbols = set(self.tracker.symbol_sel.symbols)
            if symbols and len(self.mi.symbol_info) == 0:
                logger.info(f"[trader] 首次获取到 {len(symbols)} 个标的，刷新市场信息…")
                await refresh_market_info(self.mi, symbols, proxy=self._proxy, live=_trader_cfg.LIVE_TRADING_ON)
                logger.info(f"[trader] 市场信息已刷新，symbol_info 数量: {len(self.mi.symbol_info)}")
                break
            if symbols:
                break
            await asyncio.sleep(1)
        
        # 定期刷新
        while not self._stop.is_set():
            await asyncio.sleep(MARKET_INFO_REFRESH_H * 3600)
            if hasattr(self.tracker, "symbol_sel"):
                symbols = set(self.tracker.symbol_sel.symbols)
            if symbols:
                await refresh_market_info(self.mi, symbols, proxy=self._proxy, live=_trader_cfg.LIVE_TRADING_ON)

    # ─── 辅助 ────────────────────────────────────────────────────────────────

    def _schedule_exit(self, pos: Position, pnl_pct: float, reason: str) -> None:
        """统一调度平仓任务，自动清理完成后的引用，防止 _exit_tasks 无限增长。"""
        pos_id = pos.id
        task = self._loop.create_task(self._do_exit(pos, pnl_pct, reason))
        self._exit_tasks[pos_id] = task
        task.add_done_callback(lambda t: self._exit_tasks.pop(pos_id, None))

    def _net_funding_rate(self, pos: "Position") -> float:
        """返回持仓的净资金费率（正=有利，负=不利）。long: 做多小所空大所；short反之。"""
        sr = self.mi.get_funding_rate(pos.small_exchange, pos.symbol)
        br = self.mi.get_funding_rate(pos.big_exchange,   pos.symbol)
        return (br - sr) if pos.direction == "long" else (sr - br)

    def _compute_pnl_pct(self, pos: "Position", small_mid: float, big_mid: float) -> float:
        """双腿合并未实现 PnL（%，相对总名义价值，不含手续费）。"""
        notional = 0.0
        if pos.small_leg:
            notional += pos.small_leg.size_usdt
        if pos.big_leg:
            notional += pos.big_leg.size_usdt
        if notional <= 0:
            return 0.0
        return pos.unrealized_pnl(small_mid, big_mid) / notional * 100.0

    def _check_exit_reason(self, pos: "Position", pnl_pct: float) -> str:
        # 1. 费率不利 → 结算前 FUNDING_EXIT_BEFORE_S 秒平仓
        if self._net_funding_rate(pos) < 0:
            secs_left = _seconds_to_next_funding()
            if secs_left <= FUNDING_EXIT_BEFORE_S:
                return "funding_exit"
        # 2. 兜底超时（极长，正常不触发）
        if pos.hold_seconds >= MAX_HOLD_SECONDS:
            return "timeout"
        # 3. 止盈：双腿合并 PnL >= TAKE_PROFIT_PCT
        if pnl_pct >= TAKE_PROFIT_PCT:
            return "convergence"
        # 4. 止损：双腿合并 PnL <= -STOP_LOSS_PCT（宽松兜底）
        if pnl_pct <= -STOP_LOSS_PCT:
            return "stop_loss"
        return ""

    async def _emergency_close(
        self,
        ev: MarketEvent,
        small_res: OrderResult,
        big_res: OrderResult,
        small_sym: str,
        big_sym: str,
        small_side: str,
        big_side: str,
    ):
        """一腿成功一腿失败时，撤销已成交的腿以恢复 delta 中性。"""
        tasks = []
        if small_res.success and small_res.fill_size > 0:
            rev = "sell" if small_side == "buy" else "buy"
            tasks.append(self.clients[ev.small_exchange].place_order(
                symbol=small_sym, side=rev, target_qty=small_res.fill_size,
                ref_price=ev.small_mid,
                symbol_info=self.mi.get_symbol_info(ev.small_exchange, ev.symbol),
                reduce_only=True,
            ))
        if big_res.success and big_res.fill_size > 0:
            rev = "sell" if big_side == "buy" else "buy"
            tasks.append(self.clients[ev.big_exchange].place_order(
                symbol=big_sym, side=rev, target_qty=big_res.fill_size,
                ref_price=ev.big_mid,
                symbol_info=self.mi.get_symbol_info(ev.big_exchange, ev.symbol),
                reduce_only=True,
            ))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception) or (hasattr(r, "success") and not r.success):
                    err = str(r) if isinstance(r, Exception) else r.error
                    logger.error(f"[trader] 紧急平仓失败（需人工处理）: {err}")

    async def load_legacy_positions(self) -> None:
        """
        启动时从各所拉取已有持仓，按 symbol 匹配大所/小所两腿，
        重建 Position 对象纳入 PM，与新开仓统一用 PnL 监控平仓。
        """
        from clients import BIG_EXCHANGES, SMALL_EXCHANGES
        BIG  = set(BIG_EXCHANGES)   # {"binance", "okx"}
        SMALL = set(SMALL_EXCHANGES) # {"gate", "bitget"}

        def _sym_canonical(ex: str, raw_sym: str) -> str:
            """将各所 symbol 格式统一为 Binance 格式（如 BSBUSDT）。"""
            if ex == "okx":
                # "BSB-USDT-SWAP" → "BSBUSDT"
                parts = raw_sym.split("-")
                return parts[0] + parts[1] if len(parts) >= 2 else raw_sym
            if ex == "gate":
                # "BSB_USDT" → "BSBUSDT"
                return raw_sym.replace("_", "")
            return raw_sym  # binance / bitget already correct

        def _parse_leg(ex: str, raw: dict) -> tuple[str, str, float, float, str]:
            """返回 (canonical_sym, exchange_sym, size_base, entry_price, side)。"""
            try:
                if ex == "binance":
                    raw_sym = raw.get("symbol", "")
                    amt     = float(raw.get("positionAmt", 0))
                    entry   = float(raw.get("entryPrice", 0))
                    side    = "buy" if amt > 0 else "sell"
                    return _sym_canonical(ex, raw_sym), raw_sym, abs(amt), entry, side
                elif ex == "okx":
                    raw_sym = raw.get("instId", "")
                    contracts = abs(float(raw.get("pos", 0)))
                    entry   = float(raw.get("avgPx", 0))
                    ct_val  = float(raw.get("ctVal", 1.0))
                    side    = "buy" if float(raw.get("pos", 0)) > 0 else "sell"
                    return _sym_canonical(ex, raw_sym), raw_sym, contracts * ct_val, entry, side
                elif ex == "gate":
                    raw_sym = raw.get("contract", "")
                    size    = float(raw.get("size", 0))
                    entry   = float(raw.get("entry_price", 0))
                    ct_val  = float(raw.get("quanto_multiplier", 1.0))
                    side    = "buy" if size > 0 else "sell"
                    return _sym_canonical(ex, raw_sym), raw_sym, abs(size) * ct_val, entry, side
                elif ex == "bitget":
                    raw_sym  = raw.get("symbol", "")
                    total    = float(raw.get("total", 0))
                    entry    = float(raw.get("openPriceAvg", 0))
                    hold     = raw.get("holdSide", "long")
                    side     = "buy" if hold == "long" else "sell"
                    return _sym_canonical(ex, raw_sym), raw_sym, total, entry, side
            except Exception:
                pass
            return "", "", 0.0, 0.0, ""

        # 拉取各所持仓
        all_legs: dict[str, list] = {}  # canonical_sym → [(ex, raw_sym, size, entry, side)]
        for ex, client in self.clients.items():
            try:
                positions = await client.get_positions()
                for raw in positions:
                    canon, ex_sym, size, entry, side = _parse_leg(ex, raw)
                    if not canon or size <= 0 or entry <= 0:
                        continue
                    all_legs.setdefault(canon, []).append((ex, ex_sym, size, entry, side))
            except Exception as e:
                logger.warning(f"[trader] 加载旧持仓时 {ex} 查询失败: {e}")

        # 按 symbol 匹配大所 + 小所两腿
        loaded = 0
        for canon_sym, legs in all_legs.items():
            big_legs   = [(ex, es, sz, ep, sd) for ex, es, sz, ep, sd in legs if ex in BIG]
            small_legs = [(ex, es, sz, ep, sd) for ex, es, sz, ep, sd in legs if ex in SMALL]
            if not big_legs or not small_legs:
                continue  # 找不到配对（单边敞口，不自动纳入）
            b_ex, b_sym, b_sz, b_entry, b_side = big_legs[0]
            s_ex, s_sym, s_sz, s_entry, s_side = small_legs[0]

            # 方向：small 腿买入 = long；small 腿卖出 = short
            direction = "long" if s_side == "buy" else "short"

            small_leg = Leg(
                exchange=s_ex, symbol=s_sym, side=s_side,
                order_id="", entry_price=s_entry,
                size_base=s_sz, size_usdt=s_sz * s_entry,
            )
            big_leg = Leg(
                exchange=b_ex, symbol=b_sym, side=b_side,
                order_id="", entry_price=b_entry,
                size_base=b_sz, size_usdt=b_sz * b_entry,
            )
            pos = Position(
                symbol=canon_sym, big_exchange=b_ex, small_exchange=s_ex,
                direction=direction, small_leg=small_leg, big_leg=big_leg,
                open_anomaly_pct=0.0,
            )
            self.pm.add_position(pos)
            loaded += 1
            logger.info(
                f"[trader] 加载旧持仓 {pos.id} | {canon_sym} {b_ex}/{s_ex}"
                f" | dir={direction} | small_entry={s_entry} big_entry={b_entry}"
            )

        if loaded:
            logger.info(f"[trader] 共加载 {loaded} 笔旧持仓，热身后与新仓统一 PnL 监控")
        else:
            logger.info("[trader] 各所无旧持仓需要加载")

    async def _close_all_clients(self):
        for client in self.clients.values():
            try:
                await client.close()
            except Exception:
                pass
        try:
            await self.ob.close()
        except Exception:
            pass


def _seconds_to_next_funding() -> float:
    """
    返回距离下一个资金费结算时间点的秒数。
    Binance/OKX/Gate/Bitget 均为每 8 小时结算一次：UTC 0:00 / 8:00 / 16:00。
    """
    now_utc = time.time() % 86400   # 当天已过秒数（UTC）
    for t in (0, 28800, 57600, 86400):
        if t > now_utc:
            return t - now_utc
    return 86400 - now_utc
