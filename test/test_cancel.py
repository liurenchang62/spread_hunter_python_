"""
测试限价单撤单流程：
  1. 挂一笔远离市价的限价单（不会成交）
  2. 查询挂单列表，确认订单存在
  3. 调用 cancel_order() 撤单
  4. 再次查询挂单列表，确认已撤销

用法：
    python -m test.test_cancel
    python -m test.test_cancel --ex binance
"""
import argparse
import asyncio

from test._common import *


async def _test_one(name: str, client, symbol: str, btc_price: float):
    print(f"\n  [{name.upper()}]  {symbol}")

    qty = MIN_QTY.get(name, 0.001)
    # 挂单价格设为市价的 95%，确保不会成交（买价低于市价）
    # 同时确保名义价值 >= 50 USDT（Binance 最小要求）
    # 对于 BTC@76000, 0.001 BTC = 76 USDT > 50 USDT ✓
    limit_price = round(btc_price * 0.95, 1)
    notional = qty * limit_price
    info(f"挂限价买单 qty={qty} price={limit_price:.1f} 名义价值≈{notional:.1f} USDT（低于市价，不会成交）")

    res = await client.place_limit_order(
        symbol=symbol, side="buy",
        target_qty=qty, limit_price=limit_price,
    )
    if not res.success:
        fail(f"挂单失败: {res.error}")
        return
    ok(f"挂单成功 | order_id={res.order_id}")
    order_id = res.order_id

    # ── 查询挂单（Gate 测试网可能需要更长延迟才能看到新订单）
    wait_sec = 2.0 if name == "gate" else 0.5
    await asyncio.sleep(wait_sec)
    orders = await client.get_open_orders(symbol=symbol)
    matched = [o for o in orders if str(o.get("orderId") or o.get("ordId") or o.get("id") or "") == str(order_id)]
    if matched:
        ok(f"挂单查询到 | 共 {len(orders)} 笔挂单，目标订单存在")
    else:
        warn(f"挂单查询：共 {len(orders)} 笔，未找到目标订单 id={order_id}（可能订单 ID 格式差异）")

    # ── 撤单
    info(f"撤销订单 {order_id}")
    cancelled = await client.cancel_order(symbol=symbol, order_id=str(order_id))
    if cancelled:
        ok("撤单成功")
    else:
        fail("撤单失败（可能已被成交或 ID 格式不匹配）")

    # ── 确认已撤
    await asyncio.sleep(0.5)
    orders_after = await client.get_open_orders(symbol=symbol)
    still_open = [o for o in orders_after if str(o.get("orderId") or o.get("ordId") or o.get("id") or "") == str(order_id)]
    if still_open:
        warn(f"撤单后仍查询到订单，请手动检查")
    else:
        ok("撤单后确认：订单已不在挂单列表")


async def main(targets: list[str]):
    clients = load_clients()
    section("限价单撤单测试")

    btc_price = await get_btc_price(proxy=PROXY_URL)
    info(f"BTC 参考价: {btc_price:.2f} USDT")

    for name, client in clients.items():
        if targets and name not in targets:
            continue
        symbol = TEST_SYMBOL.get(name, "BTCUSDT")
        try:
            await _test_one(name, client, symbol, btc_price)
        except Exception as e:
            fail(f"{name} 撤单测试异常: {e}")

    for c in clients.values():
        await c.close()
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="限价单撤单测试")
    parser.add_argument("--ex", help="只测某交易所")
    args = parser.parse_args()
    targets = [args.ex] if args.ex else []
    asyncio.run(main(targets))
