"""
成本模型：在开仓前估算本次交易的净利润（USDT）和 ROI。

所有中间计算均使用绝对值（USDT），最后才算比率，避免基数歧义。

调用方式：
    result = evaluate(ev, big, small, mi)
    if result.should_trade:
        place_orders(result.target_qty, ...)
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("trader.cost")

from tracker.models import MarketEvent
from trader.config import (
    CONVERGENCE_PCT,
    HOLD_ESTIMATE_S,
    MIN_NET_ROI,
    MIN_ORDER_NOTIONAL_USDT,
    PAIR_CAPITAL_FALLBACK_USDT,
    SLIPPAGE_MULTIPLIER,
)
from trader.market_info import MarketInfo
from trader.orderbook import OrderBook, walk_slippage


@dataclass
class CostResult:
    should_trade:    bool
    target_qty:      float   # base coin 数量（两腿统一）
    gross_usdt:      float   # 毛利润（USDT）
    fee_usdt:        float   # 手续费合计（USDT）
    slippage_usdt:   float   # 滑点估算（USDT）
    funding_usdt:    float   # 资金费率（USDT）
    net_profit_usdt: float   # 净利润（USDT）
    net_roi:         float   # 净 ROI（相对单腿资金）
    reason:          str     # 不交易时的原因


def evaluate(
    ev: MarketEvent,
    big: str,
    small: str,
    mi: MarketInfo,
    leg_budget: float | None = None,
    small_ob: Optional[OrderBook] = None,
    big_ob:   Optional[OrderBook] = None,
) -> CostResult:
    """
    基于当前 MarketEvent 估算本次开仓的预期净利润。

    leg_budget: 单腿资金上限（USDT）。
    small_ob / big_ob: 真实订单薄（走单计算滑点）；None 时回退到 BBO × 系数估算。

    方向 long：小所买入，大所卖空（对冲）。
    方向 short：小所卖空，大所买入（对冲）。
    """
    if leg_budget is None:
        leg_budget = PAIR_CAPITAL_FALLBACK_USDT / 2.0

    # 1. 确定开仓参考价格
    #    小所 long：以 ask 买入；small short：以 bid 卖出
    #    大所对冲方向相反：long 时大所卖空（以 bid 出），short 时大所买入（以 ask 进）
    if ev.direction == "long":
        p_small = ev.small_ask
        p_big   = ev.big_bid
    else:
        p_small = ev.small_bid
        p_big   = ev.big_ask

    if p_small <= 0 or p_big <= 0:
        return _reject("价格数据无效", 0.0, 0.0)

    # 2. 计算 target_qty（两腿取最小可下单量，统一用 base coin）
    qty_small = mi.calc_target_qty(small, ev.symbol, leg_budget, p_small)
    qty_big   = mi.calc_target_qty(big,   ev.symbol, leg_budget, p_big)

    if qty_small <= 0 or qty_big <= 0:
        return _reject("lot size 数据缺失或预算不足", 0.0, 0.0)

    target_qty = min(qty_small, qty_big)

    # 校验两腿实际名义价值均满足最小下单要求
    notional_small = target_qty * p_small
    notional_big   = target_qty * p_big
    if notional_small < MIN_ORDER_NOTIONAL_USDT or notional_big < MIN_ORDER_NOTIONAL_USDT:
        return _reject(
            f"名义价值不足: small={notional_small:.2f}U big={notional_big:.2f}U "
            f"(min={MIN_ORDER_NOTIONAL_USDT}U)",
            target_qty, 0.0,
        )

    # 3. 毛利润
    #    gross = target_qty × p_small × (A - C) / 100
    A = abs(ev.anomaly_pct)
    C = CONVERGENCE_PCT
    if A <= C:
        return _reject(f"anomaly {A:.3f}% <= convergence {C}%", target_qty, 0.0)

    gross_usdt = target_qty * p_small * (A - C) / 100.0

    # 4. 手续费（4 笔吃单：小所进 + 大所进 + 小所出 + 大所出）
    fee_small = mi.get_taker_fee(small)
    fee_big   = mi.get_taker_fee(big)
    fee_entry = target_qty * p_small * fee_small + target_qty * p_big * fee_big
    fee_exit  = fee_entry   # 出场价与入场价近似相等
    fee_usdt  = fee_entry + fee_exit

    # 5. 滑点
    #    优先：用真实订单薄走单计算（进场 + 出场各一次）
    #    回退：BBO 价差 × 保守系数（订单薄不可用时）
    small_side = "buy"  if ev.direction == "long" else "sell"
    big_side   = "sell" if ev.direction == "long" else "buy"
    budget_small = target_qty * p_small
    budget_big   = target_qty * p_big

    if small_ob and small_ob.asks and small_ob.bids:
        small_levels = small_ob.asks if small_side == "buy" else small_ob.bids
        small_entry_slip = walk_slippage(small_side, small_levels, budget_small)
    else:
        logger.warning(f"[cost] 订单薄不可用，回退BBO估算滑点 | {ev.symbol} small={small}")
        spread_frac = (ev.small_ask - ev.small_bid) / ev.small_mid if ev.small_mid > 0 else 0.001
        small_entry_slip = budget_small * spread_frac * SLIPPAGE_MULTIPLIER

    if big_ob and big_ob.asks and big_ob.bids:
        big_levels = big_ob.bids if big_side == "sell" else big_ob.asks
        big_entry_slip = walk_slippage(big_side, big_levels, budget_big)
    else:
        logger.warning(f"[cost] 订单薄不可用，回退BBO估算滑点 | {ev.symbol} big={big}")
        spread_frac = (ev.big_ask - ev.big_bid) / ev.big_mid if ev.big_mid > 0 else 0.001
        big_entry_slip = budget_big * spread_frac * SLIPPAGE_MULTIPLIER

    # 出场滑点 ≈ 进场滑点（保守）
    slip_usdt = (small_entry_slip + big_entry_slip) * 2

    # 6. 资金费率（两腿，按估计持仓时长折算）
    fr_small  = mi.get_funding_rate(small, ev.symbol)
    fr_big    = mi.get_funding_rate(big,   ev.symbol)
    funding_usdt = (
        target_qty * p_small * abs(fr_small) * HOLD_ESTIMATE_S / 28800.0
        + target_qty * p_big   * abs(fr_big)   * HOLD_ESTIMATE_S / 28800.0
    )

    # 7. 净利润和 ROI
    net_profit_usdt = gross_usdt - fee_usdt - slip_usdt - funding_usdt
    leg_actual_usdt = target_qty * p_small
    net_roi = net_profit_usdt / leg_actual_usdt if leg_actual_usdt > 0 else 0.0

    # 8. 决策（仅使用净 ROI 作为门槛，净利润仅用于日志展示）
    if net_roi < MIN_NET_ROI:
        return CostResult(
            should_trade=False, target_qty=target_qty,
            gross_usdt=gross_usdt, fee_usdt=fee_usdt,
            slippage_usdt=slip_usdt, funding_usdt=funding_usdt,
            net_profit_usdt=net_profit_usdt, net_roi=net_roi,
            reason=f"净ROI {net_roi:.4%} < 门槛 {MIN_NET_ROI:.2%} (净利润{net_profit_usdt:.4f} USDT)",
        )

    return CostResult(
        should_trade=True, target_qty=target_qty,
        gross_usdt=gross_usdt, fee_usdt=fee_usdt,
        slippage_usdt=slip_usdt, funding_usdt=funding_usdt,
        net_profit_usdt=net_profit_usdt, net_roi=net_roi,
        reason="",
    )


def _reject(reason: str, target_qty: float, gross: float) -> CostResult:
    return CostResult(
        should_trade=False, target_qty=target_qty,
        gross_usdt=gross, fee_usdt=0.0,
        slippage_usdt=0.0, funding_usdt=0.0,
        net_profit_usdt=0.0, net_roi=0.0,
        reason=reason,
    )
