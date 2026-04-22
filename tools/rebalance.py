"""
资金再平衡脚本。

功能：
  1. 查询各交易所合约账户 + 现货/资金账户 USDT 余额
  2. 若最富裕交易所余额 - 平均值 > 300 USDT，触发再平衡
  3. 将多余资金从合约账户划转到现货/资金账户
  4. 查询提现手续费（SOL vs BSC），选择更低的网络
     - 若查不到手续费：优先走 SOL（一般费用最低）
     - 若目标交易所不支持 SOL：改走 BSC
  5. 按每笔 >= 100 USDT 的最小金额执行提现，均摊到其他交易所

用法：
  python tools/rebalance.py             # 干跑：只显示计划，不操作
  python tools/rebalance.py --execute   # 实际执行（每步需要输入确认）

请在各交易所完成 API 白名单与资金密码等网页端设置；脚本仅通过官方 API 调用。
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiohttp

from clients.withdrawal_addresses import (
    get_deposit_address,
    get_supported_networks,
    PREFERRED_NETWORKS,
)
from trader.exchange_client import build_clients

# ─── 常量 ────────────────────────────────────────────────────────────────────
TRIGGER_THRESHOLD = 300.0   # 最富裕所余额 - 平均值 超过此值才触发（USDT）
MIN_WITHDRAWAL    = 100.0   # 每笔提现最低金额（USDT）
FEE_RESERVE       = 5.0     # 提现前在现货账户预留的额外缓冲（覆盖手续费）
COMPARE_NETWORKS  = ["SOL", "BSC"]  # 优先比较这两个网络的手续费

# ─── 颜色输出 ─────────────────────────────────────────────────────────────────
R = "\033[31m"
G = "\033[32m"
Y = "\033[33m"
C = "\033[36m"
W = "\033[0m"


def _ok(msg: str):  print(f"  {G}✓{W} {msg}")
def _warn(msg: str): print(f"  {Y}⚠ {W}{msg}")
def _err(msg: str):  print(f"  {R}✗{W} {msg}")
def _info(msg: str): print(f"  {C}→{W} {msg}")


def _confirm(prompt: str, execute: bool) -> bool:
    """干跑时直接返回 True（不实际操作），实际执行时需要用户确认。"""
    if not execute:
        return True   # dry-run：假装确认
    resp = input(f"  {Y}[确认]{W} {prompt} (输入 yes 执行): ")
    return resp.strip().lower() == "yes"


# ─── 余额查询 ─────────────────────────────────────────────────────────────────

async def _fetch_balances(clients: dict) -> dict[str, dict]:
    """
    并发查询各所合约 + 现货余额。
    返回 {exchange: {"futures": float, "spot": float, "total": float}}
    """
    async def _query(ex: str, client) -> tuple[str, float, float]:
        try:
            futures = await client.get_balance()
        except Exception as e:
            _warn(f"{ex} 合约余额查询失败: {e}")
            futures = 0.0
        try:
            spot = await client.get_spot_balance()
        except Exception as e:
            _warn(f"{ex} 现货余额查询失败: {e}")
            spot = 0.0
        return ex, futures, spot

    tasks = [_query(ex, c) for ex, c in clients.items()]
    results = await asyncio.gather(*tasks)
    return {
        ex: {"futures": f, "spot": s, "total": f + s}
        for ex, f, s in results
    }


# ─── 手续费查询 ───────────────────────────────────────────────────────────────

async def _fetch_fees(client, networks: list[str]) -> dict[str, Optional[float]]:
    """查询指定网络的提现手续费，返回 {network: fee_usdt}。"""
    results = {}
    for net in networks:
        try:
            fee = await client.get_withdrawal_fee(net)
            results[net] = fee
        except Exception:
            results[net] = None
    return results


def _pick_network(source: str, target: str, fees: dict[str, Optional[float]]) -> tuple[str, float]:
    """
    选择最优提现网络。
    1. 优先比较 SOL vs BSC 手续费
    2. 如果费用不可用或目标不支持某网络，则跳过
    3. 最终回退到 SOL（如果 target 支持），否则 BSC，否则第一个可用网络

    返回 (network, estimated_fee)
    """
    supported = get_supported_networks(source, target)
    if not supported:
        return "", 0.0

    # 有手续费信息时，比较并选择最低的
    best_net, best_fee = "", float("inf")
    for net in COMPARE_NETWORKS:
        if net not in supported:
            continue
        fee = fees.get(net)
        if fee is not None and fee < best_fee:
            best_fee = fee
            best_net = net

    if best_net:
        return best_net, best_fee

    # 费用信息不可用时：按优先级选第一个 supported 网络
    fallback = next((n for n in ["SOL", "BSC", "TRX"] if n in supported), supported[0])
    _warn(f"手续费信息不可用，默认使用 {fallback} 网络（经验最低费）")
    return fallback, 0.0


# ─── 划转计划 ─────────────────────────────────────────────────────────────────

def _plan_rebalance(balances: dict[str, dict]) -> tuple[str, list[dict]]:
    """
    计算再平衡计划。
    返回 (source_exchange, [{target, amount}, ...])
    source_exchange: 余额最多的交易所
    每个目标的 amount 已考虑最小提现金额限制。
    """
    if not balances:
        return "", []

    totals = {ex: v["total"] for ex, v in balances.items()}
    avg    = sum(totals.values()) / len(totals)
    source = max(totals, key=totals.get)
    surplus = totals[source] - avg

    if surplus <= TRIGGER_THRESHOLD:
        return source, []   # 不触发

    # 计算每个目标应该收到多少
    targets = []
    for ex, total in totals.items():
        if ex == source:
            continue
        deficit = avg - total
        if deficit >= MIN_WITHDRAWAL:
            targets.append({"exchange": ex, "amount": round(deficit, 2)})

    return source, targets


# ─── 主流程 ───────────────────────────────────────────────────────────────────

async def run(execute: bool):
    print(f"\n{C}{'='*60}{W}")
    print(f"{C}  Spread Hunter — 资金再平衡{W}")
    mode_label = f"{R}实际执行{W}" if execute else f"{G}干跑模式（不实际操作）{W}"
    print(f"  模式：{mode_label}")
    print(f"{C}{'='*60}{W}\n")

    # 构建实盘客户端（再平衡只针对真实资金）
    clients = build_clients(live=True, proxy="")
    if not clients:
        _err("无法加载实盘 API Key，请检查 clients/api_keys_live.py")
        return

    # ── Step 1: 查询余额 ───────────────────────────────────────────────────
    print(f"{C}[1/5] 查询各交易所余额…{W}")
    balances = await _fetch_balances(clients)

    print(f"\n  {'交易所':<10} {'合约':>10} {'现货':>10} {'合计':>10}")
    print(f"  {'-'*44}")
    for ex, v in sorted(balances.items()):
        print(f"  {ex:<10} {v['futures']:>10.2f} {v['spot']:>10.2f} {v['total']:>10.2f}")
    avg = sum(v["total"] for v in balances.values()) / len(balances) if balances else 0
    print(f"  {'平均':>44.2f}".replace(f"{'平均':>44.2f}", f"  {'平均':<10} {'':>10} {'':>10} {avg:>10.2f}"))

    # ── Step 2: 判断是否需要再平衡 ─────────────────────────────────────────
    print(f"\n{C}[2/5] 判断再平衡条件…{W}")
    source, plan = _plan_rebalance(balances)

    if not plan:
        richest = max(balances, key=lambda ex: balances[ex]["total"]) if balances else ""
        surplus = (balances[richest]["total"] - avg) if richest else 0
        _ok(f"无需再平衡（最富裕所:{richest} 余额:{balances.get(richest,{}).get('total',0):.2f},"
            f" 超出均值:{surplus:.2f} < 阈值:{TRIGGER_THRESHOLD}）")
        await _close_clients(clients)
        return

    source_bal = balances[source]
    _warn(f"触发再平衡！来源: {source} | "
          f"总余额:{source_bal['total']:.2f} USDT | 均值:{avg:.2f} USDT")
    print(f"\n  提现计划:")
    for p in plan:
        print(f"    → {p['exchange']:<10} {p['amount']:>8.2f} USDT")

    total_to_send = sum(p["amount"] for p in plan)
    print(f"    合计发出: {total_to_send:.2f} USDT")

    # ── Step 3: 将合约余额划转到现货/资金账户 ──────────────────────────────
    print(f"\n{C}[3/5] 划转合约 → 现货/资金账户…{W}")
    needed_spot = total_to_send + FEE_RESERVE
    current_spot = source_bal["spot"]
    to_transfer  = max(0.0, needed_spot - current_spot)

    if to_transfer > source_bal["futures"]:
        _err(f"合约余额不足！需划转:{to_transfer:.2f} USDT, 合约可用:{source_bal['futures']:.2f} USDT")
        await _close_clients(clients)
        return

    if to_transfer > 0:
        _info(f"从 {source} 合约划转 {to_transfer:.2f} USDT 至现货")
        if _confirm(f"划转 {to_transfer:.2f} USDT ({source} 合约→现货)", execute):
            if execute:
                ok = await clients[source].transfer_to_spot(to_transfer)
                if ok:
                    _ok(f"划转成功 {to_transfer:.2f} USDT")
                else:
                    _err("划转失败，请手动操作后重试")
                    await _close_clients(clients)
                    return
            else:
                _info("[DRY-RUN] 跳过实际划转")
    else:
        _ok(f"现货余额充足（{current_spot:.2f} USDT），无需划转")

    # ── Step 4: 查询提现手续费 ─────────────────────────────────────────────
    print(f"\n{C}[4/5] 查询 {source} 提现手续费…{W}")
    src_client = clients[source]
    fees = await _fetch_fees(src_client, COMPARE_NETWORKS)
    for net, fee in fees.items():
        if fee is not None:
            _info(f"{net}: {fee:.2f} USDT/笔")
        else:
            _warn(f"{net}: 费用信息不可用")

    # ── Step 5: 执行提现 ───────────────────────────────────────────────────
    print(f"\n{C}[5/5] 执行提现…{W}")
    success_count = 0
    fail_count    = 0

    for p in plan:
        target    = p["exchange"]
        amount    = p["amount"]
        network, est_fee = _pick_network(source, target, fees)

        if not network:
            _err(f"→ {target}: 找不到共同支持的提现网络，跳过")
            fail_count += 1
            continue

        address = get_deposit_address(target, network)
        if not address:
            _err(f"→ {target}: 没有配置 {network} 充值地址，跳过")
            fail_count += 1
            continue

        # 手续费从提现金额中扣除（实际到账 = amount - fee）
        fee_actual = est_fee if est_fee > 0 else 1.0   # 未知费用默认按1U保守估算
        net_amount = amount - fee_actual
        if net_amount < MIN_WITHDRAWAL * 0.8:
            _warn(f"→ {target}: 扣除手续费后({net_amount:.2f}U)低于最小金额，跳过")
            fail_count += 1
            continue

        fee_str = f"{est_fee:.2f}" if est_fee > 0 else "≈1.00(估算)"
        print(f"\n  → {target}")
        print(f"     网络  : {network}")
        print(f"     地址  : {address}")
        print(f"     金额  : {amount:.2f} USDT (手续费:{fee_str} USDT)")
        print(f"     预计到账: {net_amount:.2f} USDT")

        if not _confirm(f"提现 {amount:.2f} USDT → {target} via {network}", execute):
            _warn(f"用户跳过 → {target}")
            continue

        if execute:
            result = await src_client.withdraw(network, address, amount)
            if result["success"]:
                _ok(f"提现成功！订单ID: {result['id']}")
                success_count += 1
            else:
                _err(f"提现失败: {result['error']}")
                fail_count += 1
            # 两笔提现之间稍作等待，避免触发频率限制
            await asyncio.sleep(2.0)
        else:
            _info(f"[DRY-RUN] 跳过实际提现 → {target} {amount:.2f} USDT via {network}")
            success_count += 1

    # ── 总结 ──────────────────────────────────────────────────────────────
    print(f"\n{C}{'='*60}{W}")
    if execute:
        print(f"  再平衡完成：成功 {success_count} 笔 / 失败 {fail_count} 笔")
        if fail_count > 0:
            _warn("部分提现失败，请手动检查交易所账户并补充操作")
    else:
        print(f"  [DRY-RUN] 计划预览完毕：{success_count} 笔提现 / {fail_count} 笔无法执行")
        print(f"  使用 --execute 参数实际运行")
    print(f"{C}{'='*60}{W}\n")

    await _close_clients(clients)


async def _close_clients(clients: dict):
    for c in clients.values():
        try:
            await c.close()
        except Exception:
            pass


# ─── 入口 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Spread Hunter 资金再平衡脚本")
    parser.add_argument(
        "--execute", action="store_true",
        help="实际执行（默认为干跑模式，仅显示计划）"
    )
    args = parser.parse_args()

    if args.execute:
        confirm = input(
            f"\n{R}警告：即将执行资金再平衡，涉及真实资金划转和提现！\n"
            f"每步操作前会单独询问确认。\n"
            f"请输入 YES 继续: {W}"
        )
        if confirm.strip() != "YES":
            print("已取消。")
            return

    asyncio.run(run(execute=args.execute))


if __name__ == "__main__":
    main()
