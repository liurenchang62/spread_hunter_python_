"""
测试市价单下单（最小数量，开仓后立即反向平仓）。

⚠️  会产生真实 Demo/Testnet 成交。每所各下一笔最小仓位，成交后自动平仓。

用法：
    python -m test.test_orders
    python -m test.test_orders --ex gate
    python -m test.test_orders --ex binance --symbol ETHUSDT
"""
import argparse
import asyncio

from test._common import *


async def _test_one(name: str, client, symbol: str, btc_price: float):
    print(f"\n  [{name.upper()}]  {symbol}")

    qty = MIN_QTY.get(name, 0.001)
    ref = btc_price

    # ── 开仓（BUY）
    info(f"买入 {qty} base (≈{qty * ref:.1f} USDT)")
    res = await client.place_order(
        symbol=symbol, side="buy",
        target_qty=qty, ref_price=ref,
    )
    if not res.success:
        fail(f"开仓失败: {res.error}")
        return
    ok(f"开仓成功 | order_id={res.order_id} fill={res.fill_price:.2f} size={res.fill_size}")

    # ── 平仓（SELL）
    close_qty = res.fill_size if res.fill_size > 0 else qty
    info(f"卖出 {close_qty} base 平仓")
    res2 = await client.place_order(
        symbol=symbol, side="sell",
        target_qty=close_qty, ref_price=res.fill_price or ref,
    )
    if not res2.success:
        warn(f"平仓失败（可能有残留持仓）: {res2.error}")
    else:
        ok(f"平仓成功 | order_id={res2.order_id} fill={res2.fill_price:.2f}")


async def main(targets: list[str], custom_symbol: str):
    clients = load_clients()
    section("市价单下单测试（开仓 + 自动平仓）")

    btc_price = await get_btc_price(proxy=PROXY_URL)
    info(f"BTC 参考价: {btc_price:.2f} USDT")

    for name, client in clients.items():
        if targets and name not in targets:
            continue
        symbol = custom_symbol or TEST_SYMBOL.get(name, "BTCUSDT")
        try:
            await _test_one(name, client, symbol, btc_price)
        except Exception as e:
            fail(f"{name} 下单测试异常: {e}")

    for c in clients.values():
        await c.close()

    warn("测试完成，请确认 Demo/Testnet 账户无残留持仓")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="市价单下单测试")
    parser.add_argument("--ex",     help="只测某交易所")
    parser.add_argument("--symbol", help="自定义合约（默认 BTCUSDT 系列）")
    args = parser.parse_args()
    targets = [args.ex] if args.ex else []
    asyncio.run(main(targets, args.symbol or ""))
