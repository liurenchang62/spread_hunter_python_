"""
实盘最小市价单测试（开仓 + 立即平仓）。

⚠️  会产生真实交易，消耗真实手续费。
每笔订单使用各所允许的最低名义价值（约 5-10 USDT/腿），
立即反向市价平仓，净亏损预计 = 2 × taker_fee × notional ≈ 0.05-0.15 USDT/所。

流程：
  1. 拉取当前 TRX 价格和合约规格，计算最小下单量
  2. 列出所有交易所将花费的金额，等待用户确认
  3. 对每个交易所单独确认后再下单

用法：
    python -m test_live.test_order
    python -m test_live.test_order --ex gate
"""

import argparse
import asyncio

from test_live._common import *
from clients.config import to_exchange_fmt


async def _place_min_order(name: str, client, exchange_symbol: str,
                           qty: float, ref_price: float, notional: float):
    """下最小买单 + 立即卖出平仓。"""
    money(f"{name.upper()}: 买入 {qty:.6f} TRX @ ≈{ref_price:.6f} ≈ {notional:.4f} USDT")

    # ── 开仓（买入）──────────────────────────────────────────────────────────
    buy_res = await client.place_order(
        symbol=exchange_symbol, side="buy",
        target_qty=qty, ref_price=ref_price,
    )
    if not buy_res.success:
        fail(f"开仓失败: {buy_res.error}")
        return False

    ok(f"开仓成功 | order_id={buy_res.order_id} "
       f"fill={buy_res.fill_price:.6f} size={buy_res.fill_size:.6f} "
       f"fee={buy_res.fee_usdt:.6f} USDT")

    # ── 平仓（卖出）──────────────────────────────────────────────────────────
    close_qty   = buy_res.fill_size if buy_res.fill_size > 0 else qty
    close_price = buy_res.fill_price if buy_res.fill_price > 0 else ref_price
    info(f"        立即平仓: 卖出 {close_qty:.6f} TRX")

    sell_res = await client.place_order(
        symbol=exchange_symbol, side="sell",
        target_qty=close_qty, ref_price=close_price,
    )
    if not sell_res.success:
        warn(f"⚠️  平仓失败！{name.upper()} 可能有残留多头持仓，请手动处理: {sell_res.error}")
        return False

    ok(f"平仓成功 | order_id={sell_res.order_id} "
       f"fill={sell_res.fill_price:.6f} size={sell_res.fill_size:.6f} "
       f"fee={sell_res.fee_usdt:.6f} USDT")

    total_fee = buy_res.fee_usdt + sell_res.fee_usdt
    pnl = (sell_res.fill_price - buy_res.fill_price) * close_qty - total_fee
    info(f"        本次手续费合计: {total_fee:.6f} USDT  |  预估盈亏: {pnl:+.6f} USDT")
    return True


async def main(targets: list[str]):
    section("实盘最小市价单测试 ⚠️ 真实资金")

    clients = load_live_clients()
    if not clients:
        return

    # ── 拉取合约规格和价格 ───────────────────────────────────────────────────
    print(f"\n  拉取 TRX 合约规格和当前价格…")
    try:
        mi = await load_market_info({TEST_SYMBOL_INTERNAL})
    except Exception as e:
        fail(f"市场信息拉取失败: {e}")
        for c in clients.values(): await c.close()
        return

    trx_price = await get_price("TRX")
    info(f"  TRX 当前价: {trx_price:.6f} USDT")

    # ── 计算各所最小下单量并汇总 ─────────────────────────────────────────────
    print(f"\n  各交易所下单计划（最小金额）：")
    plans: dict[str, tuple[float, float, str]] = {}  # name → (qty, notional, exchange_sym)

    for name in clients:
        if targets and name not in targets:
            continue
        exchange_sym = to_exchange_fmt(TEST_SYMBOL_INTERNAL, name)
        qty, notional = compute_min_qty(mi, name, TEST_SYMBOL_INTERNAL, trx_price)
        if qty <= 0:
            warn(f"  {name.upper()}: 无法计算最小下单量（合约规格缺失）")
            continue
        taker = mi.get_taker_fee(name)
        fee_est = notional * taker * 2  # 一进一出
        print(f"  {'─'*48}")
        info(f"  {name.upper():8} | {qty:.6f} TRX | 名义价值 ≈ {notional:.4f} USDT")
        info(f"           | 预估手续费 ≈ {fee_est:.6f} USDT（开+平 taker×2）")
        plans[name] = (qty, notional, exchange_sym)

    if not plans:
        fail("没有可执行的下单计划，请检查合约规格是否已加载")
        for c in clients.values(): await c.close()
        return

    total_notional = sum(n for _, n, _ in plans.values())
    print(f"  {'─'*48}")
    money(f"  合计将花费约 {total_notional:.4f} USDT 资金（立即平仓，净亏损预计仅手续费）")

    # ── 全局确认 ─────────────────────────────────────────────────────────────
    if not confirm(f"执行以上 {len(plans)} 个交易所的最小市价单测试？"):
        print("  已取消。")
        for c in clients.values(): await c.close()
        return

    # ── 逐所执行（每所单独确认）──────────────────────────────────────────────
    results = {}
    for name, (qty, notional, exchange_sym) in plans.items():
        print()
        if not confirm_each(name, f"买入 {qty:.6f} TRX ≈ {notional:.4f} USDT 并立即平仓"):
            warn(f"{name.upper()} 跳过")
            results[name] = "skip"
            continue
        try:
            ok_ = await _place_min_order(
                name, clients[name], exchange_sym, qty, trx_price, notional
            )
            results[name] = "ok" if ok_ else "partial_fail"
        except Exception as e:
            fail(f"{name} 测试异常: {e}")
            results[name] = "error"

    # ── 汇总 ─────────────────────────────────────────────────────────────────
    section("测试汇总")
    for name, r in results.items():
        if r == "ok":       ok(f"{name.upper()}: 成功")
        elif r == "skip":   info(f"  {name.upper()}: 跳过")
        elif r == "partial_fail": warn(f"{name.upper()}: 平仓失败，请手动检查持仓！")
        else:               fail(f"{name.upper()}: 异常 ({r})")

    for c in clients.values():
        await c.close()
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="实盘最小市价单测试")
    parser.add_argument("--ex", help="只测某交易所")
    args = parser.parse_args()
    asyncio.run(main([args.ex] if args.ex else []))
