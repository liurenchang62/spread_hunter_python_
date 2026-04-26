"""
查询各交易所余额，输出现金分布和流动性状态。
只读，不执行任何资金操作。

用法：
  python -m rebalance.check_balances
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rebalance._common import (
    R, G, Y, C, W, B,
    ok, warn, err, info, hdr, sep,
    load_live_clients, close_all,
    fetch_all_states, check_rebalance, check_liquidity,
    ExchangeState, RebalanceCheck, LiquidityCheck,
    _CASH_RATIO_MIN as CASH_RATIO_MIN,
    _CASH_RATIO_RESUME as CASH_RATIO_RESUME,
)
from trader.config import REBALANCE_FLOOR_PCT


def print_state_table(states: dict[str, ExchangeState]):
    n          = len(states)
    total_cash = sum(s.cash   for s in states.values())
    total_eq   = sum(s.equity for s in states.values())
    target     = total_cash / n if n else 0
    floor      = total_cash * REBALANCE_FLOOR_PCT

    print(f"\n  {'交易所':<10} {'期货可用':>10} {'现货':>8} {'现金合计':>10}"
          f"  {'占比':>7}  {'vs均值':>10}  {'期货总权益':>10}")
    sep(76)
    for ex in sorted(states.keys()):
        s    = states[ex]
        pct  = s.cash / total_cash * 100 if total_cash else 0
        diff = s.cash - target
        diff_s = f"{G}+{diff:.2f}{W}" if diff >= 0 else f"{R}{diff:.2f}{W}"
        low_mark = f" {R}◀ 低于下限{W}" if s.cash < floor else ""
        print(f"  {ex:<10} {s.available:>10.2f} {s.spot:>8.2f} {s.cash:>10.2f}"
              f"  {pct:>6.1f}%  {diff_s:>18}  {s.total_futures:>10.2f}{low_mark}")
    sep(76)
    print(f"  {'均值/合计':<10} {'':>10} {'':>8} {total_cash:>10.2f}"
          f"  {'100.0%':>7}  {'':>10}  {total_eq - sum(s.spot for s in states.values()):>10.2f}")
    print(f"\n  现金合计: {total_cash:.2f}U   权益合计: {total_eq:.2f}U"
          f"   均值: {target:.2f}U   下限: {floor:.2f}U ({REBALANCE_FLOOR_PCT*100:.0f}%)")


def print_rebalance_status(rc: RebalanceCheck):
    hdr("再平衡检查")
    print(f"  触发条件：任意交易所现金 / 总现金 < {REBALANCE_FLOOR_PCT*100:.0f}%")
    if rc.should_rebalance:
        warn(f"需要再平衡！低于下限的交易所：{rc.sinks}")
        print(f"\n  建议转账计划（来源 → 目标  金额）：")
        for sink in rc.sinks:
            deficit = rc.target_cash - 0   # placeholder，run.py 中精确计算
            print(f"    {'多个来源':>10} → {sink:<10}  ≈{rc.target_cash:.2f}U（补至均值）")
        print(f"\n  运行 {C}python -m rebalance.run{W} 查看精确计划")
    else:
        ok(f"无需再平衡  {rc.reason}")


def print_liquidity_status(lc: LiquidityCheck, currently_monitor_only: bool):
    hdr("整体流动性检查")
    bar_fill  = int(lc.cash_ratio * 40)
    bar_empty = 40 - bar_fill
    bar_color = G if lc.cash_ratio >= CASH_RATIO_RESUME else (Y if lc.cash_ratio >= CASH_RATIO_MIN else R)
    bar = f"{bar_color}{'█'*bar_fill}{'░'*bar_empty}{W}"
    print(f"  现金/权益比: [{bar}] {lc.cash_ratio*100:.1f}%")
    print(f"  进入监控模式阈值: {CASH_RATIO_MIN*100:.0f}%    退出监控模式阈值: {CASH_RATIO_RESUME*100:.0f}%")
    print(f"  {lc.reason}")

    if lc.monitor_only and not lc.recovering:
        warn("整体流动性不足 → 仅监控模式（禁止开新仓，保留平仓）")
    elif lc.recovering:
        ok("流动性已恢复 → 退出仅监控模式")
    else:
        ok("流动性正常")


async def run():
    print(f"\n{C}{'═'*65}{W}")
    print(f"{C}{B}  Spread Hunter — 余额与流动性查询{W}")
    print(f"{C}{'═'*65}{W}")

    clients = load_live_clients()

    hdr("查询各交易所状态…")
    states = await fetch_all_states(clients)
    print_state_table(states)

    rc = check_rebalance(states)
    print_rebalance_status(rc)

    lc = check_liquidity(states, currently_monitor_only=False)
    print_liquidity_status(lc, currently_monitor_only=False)

    print(f"\n{C}{'═'*65}{W}\n")
    await close_all(clients)


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
