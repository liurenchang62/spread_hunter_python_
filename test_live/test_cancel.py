"""
实盘限价单挂单 + 撤单测试（低风险，订单挂在远离市价处不会成交）。

流程：
  1. 以市价 × 50% 挂一笔限价买单（不会成交）
  2. 查询挂单确认存在
  3. 撤单
  4. 确认已撤销

⚠️  会占用少量保证金（挂单期间），撤单后立即释放。
    极低成交风险，但请确保账户有余额。

用法：
    python -m test_live.test_cancel
    python -m test_live.test_cancel --ex okx
"""

import argparse
import asyncio

from test_live._common import *
from clients.config import to_exchange_fmt


async def _test_one(name: str, client, exchange_symbol: str,
                    qty: float, ref_price: float):
    section(f"{name.upper()} — 限价单撤单测试")

    # 挂单价格 = 市价 × 50%（远低于市价，几乎不可能成交）
    limit_price = round(ref_price * 0.50, 6)
    notional    = qty * limit_price
    info(f"挂限价买单: qty={qty:.6f} TRX  price={limit_price:.6f} USDT  名义≈{notional:.4f} USDT")
    info(f"（挂单价 = 市价 {ref_price:.6f} × 50% = {limit_price:.6f}，不会成交）")

    # ── 挂单 ──────────────────────────────────────────────────────────────────
    res = await client.place_limit_order(
        symbol=exchange_symbol, side="buy",
        target_qty=qty, limit_price=limit_price,
    )
    if not res.success:
        fail(f"挂单失败: {res.error}")
        return
    ok(f"挂单成功 | order_id={res.order_id}")
    order_id = str(res.order_id)

    # ── 查询挂单 ──────────────────────────────────────────────────────────────
    await asyncio.sleep(1.0)  # 等待订单传播
    try:
        orders = await client.get_open_orders(symbol=exchange_symbol)
        matched = [o for o in orders
                   if str(o.get("orderId") or o.get("ordId") or o.get("id") or "") == order_id]
        if matched:
            ok(f"挂单查询到 | 共 {len(orders)} 笔挂单，目标订单存在")
        else:
            warn(f"挂单查询：共 {len(orders)} 笔，未找到目标 id={order_id}（可能为 ID 格式差异）")
    except Exception as e:
        warn(f"挂单查询异常: {e}")

    # ── 撤单 ──────────────────────────────────────────────────────────────────
    info(f"撤销订单 {order_id}…")
    try:
        cancelled = await client.cancel_order(symbol=exchange_symbol, order_id=order_id)
        if cancelled:
            ok("撤单成功")
        else:
            warn("撤单返回 False（可能已成交或 ID 格式问题）")
    except Exception as e:
        fail(f"撤单异常: {e}")
        return

    # ── 确认已撤 ──────────────────────────────────────────────────────────────
    await asyncio.sleep(0.5)
    try:
        orders_after = await client.get_open_orders(symbol=exchange_symbol)
        still = [o for o in orders_after
                 if str(o.get("orderId") or o.get("ordId") or o.get("id") or "") == order_id]
        if still:
            warn("撤单后仍查询到该订单，请手动检查")
        else:
            ok("撤单确认：订单不在挂单列表中")
    except Exception as e:
        warn(f"撤单后查询异常: {e}")


async def main(targets: list[str]):
    section("实盘限价单撤单测试 ⚠️ 需要账户有余额")

    clients = load_live_clients()
    if not clients:
        return

    print(f"\n  拉取 TRX 合约规格…")
    try:
        mi = await load_market_info({TEST_SYMBOL_INTERNAL})
    except Exception as e:
        fail(f"市场信息拉取失败: {e}")
        for c in clients.values(): await c.close()
        return

    trx_price = await get_price("TRX")
    info(f"  TRX 当前价: {trx_price:.6f} USDT")

    # 单次总体确认
    if not confirm("执行各所限价单挂单+撤单测试（订单不会成交，仅占用保证金几秒）？"):
        print("  已取消。")
        for c in clients.values(): await c.close()
        return

    for name, client in clients.items():
        if targets and name not in targets:
            continue
        exchange_sym = to_exchange_fmt(TEST_SYMBOL_INTERNAL, name)
        qty, _ = compute_min_qty(mi, name, TEST_SYMBOL_INTERNAL, trx_price)
        if qty <= 0:
            warn(f"{name.upper()}: 无法计算最小下单量，跳过")
            continue
        try:
            await _test_one(name, client, exchange_sym, qty, trx_price)
        except Exception as e:
            fail(f"{name} 测试异常: {e}")

    for c in clients.values():
        await c.close()
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="实盘限价单撤单测试")
    parser.add_argument("--ex", help="只测某交易所")
    args = parser.parse_args()
    asyncio.run(main([args.ex] if args.ex else []))
