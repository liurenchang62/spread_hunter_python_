"""
手动执行一次资金再平衡。

流程：
  1. 查询所有交易所余额
  2. 再平衡检查 → 若未触发则退出
  3. 查询所有手续费 → 规划转账路径
  4. 展示完整计划
  5. --execute 时逐笔执行，等待到账确认后结束

注意：
  standalone 脚本无法自动暂停正在运行的主程序。
  执行前请确保主程序未在活跃开仓，或在低活跃时段运行。

用法：
  python -m rebalance.run              # 干跑，仅展示计划
  python -m rebalance.run --execute    # 实际执行（每步确认）
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rebalance._common import (
    R, G, Y, C, W, B,
    ok, warn, err, info, hdr, sep,
    load_live_clients, close_all,
    fetch_all_states, fetch_all_fees,
    check_rebalance, check_liquidity,
    plan_transfers, Transfer, TransferPath,
    _CASH_RATIO_MIN as CASH_RATIO_MIN,
    _CASH_RATIO_RESUME as CASH_RATIO_RESUME,
)
from trader.config import (
    REBALANCE_FLOOR_PCT, REBALANCE_CONFIRM_TIMEOUT_S,
)
from clients.withdrawal_addresses import get_deposit_address


# ─── 确认辅助 ─────────────────────────────────────────────────────────────────

def _confirm(prompt: str, execute: bool) -> bool:
    if not execute:
        return True
    resp = input(f"  {Y}[确认]{W} {prompt} (yes 执行 / 其他跳过): ")
    return resp.strip().lower() == "yes"


# ─── 展示计划 ─────────────────────────────────────────────────────────────────

def show_plan(transfers: list[Transfer]):
    total_out = sum(t.amount for t in transfers)
    print(f"\n  {'来源':<10} {'目标':<10} {'金额(U)':>9}  {'路径'}")
    sep(72)
    for t in transfers:
        f = f"{t.path.fee:.4f}" if t.path.fee_known else "≈1.0"
        print(f"  {t.source:<10} {t.target:<10} {t.amount:>9.2f}  {t.path.label}")
    sep(72)
    print(f"  {'合计':<21} {total_out:>9.2f}")


# ─── 转账执行 ─────────────────────────────────────────────────────────────────

async def _transfer_to_spot(clients, source: str, amount: float, execute: bool) -> bool:
    info(f"合约→现货划转 {source}: {amount:.2f}U")
    if not _confirm(f"划转 {amount:.2f}U（{source} 合约→现货）", execute):
        return False
    if not execute:
        info("[干跑] 跳过划转")
        return True
    result = await clients[source].transfer_to_spot(amount)
    if result:
        ok(f"划转成功 {amount:.2f}U")
        return True
    err(f"划转失败，请手动操作")
    return False


async def _poll_deposit(
    clients, exchange: str, timeout_s: float, interval_s: float = 30.0
) -> bool:
    """
    轮询 exchange 的现货账户余额，检测是否有新资金到账。
    简单做法：记录到账前余额，循环查询直到余额增加或超时。
    """
    try:
        before = await clients[exchange].get_spot_balance()
    except Exception:
        before = 0.0

    elapsed = 0.0
    while elapsed < timeout_s:
        await asyncio.sleep(interval_s)
        elapsed += interval_s
        try:
            after = await clients[exchange].get_spot_balance()
            if after > before + 0.5:   # 到账超过 0.5U 视为确认
                ok(f"[{exchange}] 到账确认：现货余额 {before:.2f}→{after:.2f}U")
                return True
        except Exception:
            pass
        info(f"[{exchange}] 等待到账… ({elapsed:.0f}s/{timeout_s:.0f}s)")

    warn(f"[{exchange}] 等待超时（{timeout_s:.0f}s），可能仍在链上传输，请手动确认")
    return False


async def execute_transfers(
    clients: dict,
    transfers: list[Transfer],
    states: dict,
    execute: bool,
):
    # ── 按来源分组，先划转合约→现货 ───────────────────────────────────────────
    from collections import defaultdict
    by_source: dict[str, list[Transfer]] = defaultdict(list)
    for t in transfers:
        by_source[t.source].append(t)

    for src, src_transfers in by_source.items():
        total_out = sum(t.amount for t in src_transfers)
        spot_now  = states[src].spot
        futures_available = states[src].available
        need_transfer = max(0.0, total_out - spot_now)

        if need_transfer > 0:
            if need_transfer > futures_available:
                err(f"{src}: 合约可用余额不足（需{need_transfer:.2f}U，仅{futures_available:.2f}U）")
                return
            ok_flag = await _transfer_to_spot(clients, src, need_transfer, execute)
            if not ok_flag and execute:
                return
        else:
            ok(f"{src} 现货余额充足（{spot_now:.2f}U），无需划转")

    # ── 逐笔提现 ──────────────────────────────────────────────────────────────
    hub_steps: list[tuple[Transfer, float]] = []   # (transfer, 到hub后金额)

    for t in transfers:
        p = t.path
        fee_s = f"{p.fee:.4f}" if p.fee_known else "≈1.0"
        net_arrive = t.amount - (p.fee if p.fee_known else 1.0)

        print(f"\n  {B}→ {t.target}{W}  (来源: {t.source})")
        print(f"     路径   : {p.label}")
        print(f"     地址   : {p.address}")
        print(f"     金额   : {t.amount:.2f}U  手续费≈{fee_s}U")
        if p.kind == "direct":
            print(f"     预计到账: {net_arrive:.2f}U")
        else:
            print(f"     {Y}★ 中转第1步：资金先到 {p.dst}，到账后需完成第2步{W}")

        if not _confirm(f"提现 {t.amount:.2f}U → {t.path.dst} via {p.network}", execute):
            warn("已跳过")
            continue

        if execute:
            result = await clients[t.source].withdraw(p.network, p.address, t.amount)
            if result["success"]:
                ok(f"提现提交成功！订单ID: {result['id']}")
                if p.kind == "hub":
                    hub_steps.append((t, net_arrive))
                else:
                    # 等待直连到账
                    info(f"等待 {t.target} 到账（轮询，超时{REBALANCE_CONFIRM_TIMEOUT_S}s）…")
                    await _poll_deposit(clients, t.target, REBALANCE_CONFIRM_TIMEOUT_S)
            else:
                err(f"提现失败: {result['error']}")
            await asyncio.sleep(1.5)
        else:
            info(f"[干跑] 跳过提现 {t.amount:.2f}U → {t.path.dst}")

    # ── 中转第二步提示 ────────────────────────────────────────────────────────
    if hub_steps:
        hdr("⚠  中转路径第二步提示")
        for t, est_amount in hub_steps:
            p = t.path
            addr2 = get_deposit_address(t.target, p.hub_network)
            f2 = f"{p.hub_fee:.4f}" if p.hub_fee_known else "≈1.0"
            print(f"\n  最终目标: {B}{t.target}{W}")
            print(f"    等资金到账 {p.dst} 后（约10-30分钟）：")
            print(f"    从 {p.dst} 提现 ≈{est_amount:.2f}U  网络: {p.hub_network}  手续费≈{f2}U")
            print(f"    地址: {addr2}")


# ─── 主流程 ───────────────────────────────────────────────────────────────────

async def run(execute: bool):
    print(f"\n{C}{'═'*65}{W}")
    print(f"{C}{B}  Spread Hunter — 资金再平衡（手动执行）{W}")
    mode = f"{R}实际执行{W}" if execute else f"{G}干跑（仅预览）{W}"
    print(f"  模式: {mode}")
    print(f"{C}{'═'*65}{W}")

    clients = load_live_clients()

    hdr("[1/4] 查询余额")
    states = await fetch_all_states(clients)
    n = len(states)
    total_cash = sum(s.cash for s in states.values())
    print(f"\n  {'交易所':<10} {'现金合计':>10}  {'占比':>7}  {'期货可用':>10}  {'现货':>8}")
    sep()
    for ex in sorted(states.keys()):
        s   = states[ex]
        pct = s.cash / total_cash * 100 if total_cash else 0
        print(f"  {ex:<10} {s.cash:>10.2f}  {pct:>6.1f}%  {s.available:>10.2f}  {s.spot:>8.2f}")
    sep()
    print(f"  {'合计':<10} {total_cash:>10.2f}  {'100.0%':>7}   均值:{total_cash/n:.2f}U"
          f"  下限:{total_cash*REBALANCE_FLOOR_PCT:.2f}U({REBALANCE_FLOOR_PCT*100:.0f}%)")

    hdr("[2/4] 再平衡检查")
    rc = check_rebalance(states)
    if not rc.should_rebalance:
        ok(f"无需再平衡  {rc.reason}")
        # 仍然检查整体流动性
        lc = check_liquidity(states, currently_monitor_only=False)
        hdr("[3/4] 整体流动性检查")
        print(f"  cash_ratio = {lc.cash_ratio*100:.1f}%  {lc.reason}")
        if lc.monitor_only:
            warn("整体现金不足 → 建议减仓释放保证金")
        else:
            ok("流动性正常")
        await close_all(clients)
        return

    warn(f"触发再平衡！低于下限的交易所: {rc.sinks}")
    print(f"  总现金: {rc.total_cash:.2f}U  均值目标: {rc.target_cash:.2f}U"
          f"  下限: {rc.floor_cash:.2f}U ({REBALANCE_FLOOR_PCT*100:.0f}%)")

    hdr("[3/4] 查询手续费 + 规划路径")
    all_fees = await fetch_all_fees(clients)
    transfers = plan_transfers(rc, states, all_fees)

    if not transfers:
        err("无法规划任何转账路径（来源余量不足或无可用网络）")
        await close_all(clients)
        return

    show_plan(transfers)

    hdr("[4/4] 执行")
    await execute_transfers(clients, transfers, states, execute)

    hdr("总结")
    if execute:
        ok("再平衡操作已提交，请确认各所到账情况")
    else:
        info("干跑完成。使用 --execute 实际执行")

    print(f"\n{C}{'═'*65}{W}\n")
    await close_all(clients)


def main():
    parser = argparse.ArgumentParser(description="Spread Hunter 资金再平衡（手动）")
    parser.add_argument("--execute", action="store_true",
                        help="实际执行（默认干跑）")
    args = parser.parse_args()

    if args.execute:
        code = input(
            f"\n{R}{B}警告：即将操作真实资金！{W}\n"
            f"触发条件：某所现金 < 总现金×{REBALANCE_FLOOR_PCT*100:.0f}%\n"
            f"输入 YES 继续: "
        )
        if code.strip() != "YES":
            print("已取消。")
            return

    asyncio.run(run(execute=args.execute))


if __name__ == "__main__":
    main()
