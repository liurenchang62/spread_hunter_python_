"""
提现手续费查询 — 输出所有交易所 × 所有网络的手续费矩阵，
并枚举每对交易所的最优路径（直连 vs 中转对比）。

只读操作，不涉及任何资金转移。

用法：
  python -m rebalance.check_fees              # 查询全部 4 所，显示完整矩阵
  python -m rebalance.check_fees --ex gate    # 只查询 gate 的对外路径
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rebalance._common import (
    NETWORK_PRIORITY, ALL_NETWORKS, EXCHANGES,
    R, G, Y, C, W, B,
    REBALANCE_FEE_CEIL_PCT,
    ok, warn, err, info, hdr, sep,
    load_live_clients, close_all,
    FeeInfo, fetch_all_fees, find_best_path,
    TransferPath,
)
from clients.withdrawal_addresses import (
    ADDRESSES, get_supported_networks, get_deposit_address,
)


# ─── 单交易所费用表 ───────────────────────────────────────────────────────────

def print_exchange_fee_table(exchange: str, fee_map: dict[str, FeeInfo]):
    print(f"\n  {B}[{exchange.upper()}]{W}")
    print(f"  {'网络':<8} {'手续费(USDT)':>14}  {'可提现':>8}  {'有入账地址':>10}")
    sep()
    has_any = False
    for net in ALL_NETWORKS:
        fi = fee_map.get(net)
        if fi is None:
            continue
        if not fi.known and not fi.has_addr:
            continue   # 该所完全不支持此网络，跳过
        has_any = True
        fee_s  = f"{fi.fee:.4f}" if fi.fee is not None else f"{Y}N/A{W} "
        api_s  = f"{G}✓{W}" if fi.fee is not None else f"{Y}?{W}"
        addr_s = f"{G}✓{W}" if fi.has_addr else f"{R}✗{W}"
        print(f"  {net:<8} {fee_s:>14}  {api_s:>16}  {addr_s:>18}")
    if not has_any:
        warn("无可用网络数据")


# ─── NxN 路径矩阵 ────────────────────────────────────────────────────────────

def print_path_matrix(all_fees: dict[str, dict[str, FeeInfo]], filter_src: str | None):
    """打印所有来源→目标的最优路径对比表（含直连 vs 中转）。"""
    hdr("最优路径矩阵（直连 vs 中转对比）")
    SAMPLE_AMOUNT = 500.0   # 用于费率检查的样本金额

    exchanges = [e for e in EXCHANGES if e in all_fees]

    for src in exchanges:
        if filter_src and src != filter_src:
            continue
        print(f"\n  来源: {B}{src}{W}")
        print(f"  {'目标':<10} {'最优路径':<52} {'总费用':>10}  {'vs次优':>12}")
        sep(80)

        for tgt in exchanges:
            if tgt == src:
                continue
            best = find_best_path(src, tgt, SAMPLE_AMOUNT, all_fees)
            if best is None:
                print(f"  {tgt:<10} {R}无可用路径{W}")
                continue

            fee_s = (
                f"{best.total_fee:.4f}U"
                if _transfer_fees_fully_known(best)
                else f"{Y}≈est{W}"
            )

            second_label = ""
            if best.kind == "direct":
                hub_best = _find_best_hub_only(src, tgt, all_fees, SAMPLE_AMOUNT)
                if hub_best:
                    hf = (
                        f"{hub_best.total_fee:.4f}U"
                        if _transfer_fees_fully_known(hub_best)
                        else "≈est"
                    )
                    diff = hub_best.total_fee - best.total_fee
                    second_label = (
                        f"中转via{hub_best.dst}={hf} "
                        f"({'贵' if diff > 0 else '便宜'}{abs(diff):.4f}U)"
                    )
            else:
                dir_best = _find_best_direct_only(src, tgt, all_fees, SAMPLE_AMOUNT)
                if dir_best:
                    df = (
                        f"{dir_best.total_fee:.4f}U"
                        if _transfer_fees_fully_known(dir_best)
                        else "≈est"
                    )
                    diff = best.total_fee - dir_best.total_fee
                    second_label = (
                        f"直连({dir_best.network})={df} "
                        f"({'贵' if diff < 0 else '便宜'}{abs(diff):.4f}U)"
                    )

            print(f"  {tgt:<10} {best.label:<52} {fee_s:>10}  {second_label}")


def _transfer_path_sort_key(p: TransferPath) -> tuple:
    """与 find_best_path 内排序一致。"""
    return (not p.fee_known, p.total_fee, p.kind != "direct")


def _transfer_fees_fully_known(p: TransferPath) -> bool:
    if p.kind == "direct":
        return p.fee_known
    return p.fee_known and p.hub_fee_known


def _find_best_direct_only(
    src: str, tgt: str, all_fees: dict[str, dict[str, FeeInfo]], amount: float
) -> TransferPath | None:
    """仅直连路径，最优一条（结构与 _common.find_best_path 一致）。"""
    src_fees = all_fees.get(src, {})
    best: TransferPath | None = None
    for net in NETWORK_PRIORITY:
        if net not in get_supported_networks(src, tgt):
            continue
        addr = get_deposit_address(tgt, net)
        if not addr:
            continue
        fi = src_fees.get(net)
        fee = fi.fee if (fi and fi.fee is not None) else None
        if fee is not None and amount > 0 and fee / amount > REBALANCE_FEE_CEIL_PCT:
            continue
        p = TransferPath(
            kind="direct", src=src, dst=tgt, final_dst=tgt,
            network=net, fee=fee or 0.0, fee_known=fee is not None,
            address=addr,
        )
        if best is None or _transfer_path_sort_key(p) < _transfer_path_sort_key(best):
            best = p
    return best


def _find_best_hub_only(
    src: str, tgt: str, all_fees: dict[str, dict[str, FeeInfo]], amount: float
) -> TransferPath | None:
    """仅 1-hop 中转，最优一条。"""
    src_fees = all_fees.get(src, {})
    best: TransferPath | None = None
    for hub in EXCHANGES:
        if hub in (src, tgt):
            continue
        hub_fees = all_fees.get(hub, {})
        best1: tuple[str, float, bool, str] | None = None
        for net in NETWORK_PRIORITY:
            if net not in get_supported_networks(src, hub):
                continue
            addr = get_deposit_address(hub, net)
            if not addr:
                continue
            fi = src_fees.get(net)
            fee = fi.fee if (fi and fi.fee is not None) else None
            if fee is not None and amount > 0 and fee / amount > REBALANCE_FEE_CEIL_PCT:
                continue
            if best1 is None or (fee is not None and (not best1[2] or fee < best1[1])):
                best1 = (net, fee or 0.0, fee is not None, addr)
        if best1 is None:
            continue
        best2: tuple[str, float, bool] | None = None
        for net in NETWORK_PRIORITY:
            if net not in get_supported_networks(hub, tgt):
                continue
            addr2 = get_deposit_address(tgt, net)
            if not addr2:
                continue
            fi2 = hub_fees.get(net)
            fee2 = fi2.fee if (fi2 and fi2.fee is not None) else None
            if best2 is None or (fee2 is not None and (not best2[2] or fee2 < best2[1])):
                best2 = (net, fee2 or 0.0, fee2 is not None)
        if best2 is None:
            continue
        p = TransferPath(
            kind="hub", src=src, dst=hub, final_dst=tgt,
            network=best1[0], fee=best1[1], fee_known=best1[2], address=best1[3],
            hub_network=best2[0], hub_fee=best2[1], hub_fee_known=best2[2],
        )
        if best is None or _transfer_path_sort_key(p) < _transfer_path_sort_key(best):
            best = p
    return best


# ─── 主流程 ───────────────────────────────────────────────────────────────────

async def run(args):
    print(f"\n{C}{'═'*70}{W}")
    print(f"{C}{B}  Spread Hunter — 提现手续费查询（实时 API 数据）{W}")
    print(f"{C}{'═'*70}{W}")

    clients = load_live_clients()
    try:
        print(f"\n{C}正在并发查询各交易所手续费…{W}")
        all_fees = await fetch_all_fees(clients)

        # ── 各所费用表 ──────────────────────────────────────────────────────────
        hdr("各交易所提现手续费（USDT）")
        target_ex = [args.ex] if args.ex else EXCHANGES
        for ex in target_ex:
            if ex not in all_fees:
                warn(f"{ex}: 未配置实盘 API Key 或查询失败，跳过")
                continue
            print_exchange_fee_table(ex, all_fees[ex])

        # ── 路径矩阵 ────────────────────────────────────────────────────────────
        if len(all_fees) > 1:
            print_path_matrix(all_fees, filter_src=args.ex)

        print(f"\n{C}{'═'*70}{W}")
        print(f"  注：手续费为实时 API 数据，N/A 表示该交易所 API 未返回此网络费用。")
        print(f"  所有手续费均为动态，可随网络拥堵程度随时变化。")
        print(f"{C}{'═'*70}{W}\n")
    finally:
        await close_all(clients)


def main():
    parser = argparse.ArgumentParser(description="查询各交易所 USDT 提现手续费")
    parser.add_argument("--ex", default=None, choices=EXCHANGES,
                        help="只分析指定交易所的对外路径")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
