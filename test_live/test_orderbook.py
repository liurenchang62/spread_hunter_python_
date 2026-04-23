"""
实盘订单薄获取测试（公开接口，无需 API Key，无资金风险）。

测试内容：
  - 从各所主网 REST 拉取 TRX 订单薄（20档）
  - 展示最优买一/卖一价、深度、买卖价差
  - 验证 walk_slippage 估算（模拟吃入 6 USDT 的单程滑点）

用法：
    python -m test_live.test_orderbook
    python -m test_live.test_orderbook --ex okx
    python -m test_live.test_orderbook --symbol SOLUSDT
"""

import argparse
import asyncio

from test_live._common import *
from trader.orderbook import OrderBookCache, walk_slippage


async def _test_one(name: str, symbol_internal: str, ob_cache: OrderBookCache,
                    exchange_symbol: str):
    section(f"{name.upper()} — 订单薄 ({exchange_symbol})")

    try:
        # OrderBookCache 需要两所，但单所测试时两腿传同一所
        ob_pair = await ob_cache.get_pair(name, symbol_internal, name, symbol_internal)
        ob = ob_pair.small or ob_pair.big
        if ob is None:
            fail("订单薄获取失败（返回 None）")
            return

        if not ob.asks or not ob.bids:
            warn("订单薄为空")
            return

        best_ask = ob.asks[0][0]
        best_bid = ob.bids[0][0]
        mid      = (best_ask + best_bid) / 2
        spread   = (best_ask - best_bid) / mid * 100 if mid > 0 else 0

        ok(f"获取成功 | 档数: asks={len(ob.asks)} bids={len(ob.bids)}")
        info(f"  最优卖一: {best_ask:.6f} USDT")
        info(f"  最优买一: {best_bid:.6f} USDT")
        info(f"  中间价  : {mid:.6f} USDT")
        info(f"  买卖价差: {spread:.4f}%")

        # 深度分析（前 5 档总量）
        ask_depth = sum(p * q for p, q in ob.asks[:5])
        bid_depth = sum(p * q for p, q in ob.bids[:5])
        info(f"  前5档买盘深度: {bid_depth:.2f} USDT")
        info(f"  前5档卖盘深度: {ask_depth:.2f} USDT")

        # 滑点估算（模拟吃入 6 USDT 的买单）
        budget = 6.0
        slip_buy  = walk_slippage("buy",  ob.asks, budget)
        slip_sell = walk_slippage("sell", ob.bids, budget)
        info(f"  {budget} USDT 买入滑点估算: {slip_buy:.4f} USDT ({slip_buy/budget*100:.4f}%)")
        info(f"  {budget} USDT 卖出滑点估算: {slip_sell:.4f} USDT ({slip_sell/budget*100:.4f}%)")

    except Exception as e:
        fail(f"订单薄测试失败: {e}")


async def main(targets: list[str], custom_symbol: str):
    section("订单薄获取测试（公开接口，无资金风险）")

    ob_cache = OrderBookCache(proxy="")
    symbol_internal = custom_symbol.upper().replace("-USDT-SWAP", "").replace("_USDT", "") + "USDT" \
                      if custom_symbol else TEST_SYMBOL_INTERNAL

    for name, exchange_sym in TEST_SYMBOL.items():
        if targets and name not in targets:
            continue
        if custom_symbol:
            # 用户自定义 symbol，转换为各所格式
            from clients.config import to_exchange_fmt
            exchange_sym = to_exchange_fmt(symbol_internal, name)
        try:
            await _test_one(name, symbol_internal, ob_cache, exchange_sym)
        except Exception as e:
            fail(f"{name} 订单薄测试异常: {e}")

    await ob_cache.close()
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="实盘订单薄获取测试")
    parser.add_argument("--ex",     help="只测某交易所")
    parser.add_argument("--symbol", help="自定义合约内部代码（如 SOLUSDT）")
    args = parser.parse_args()
    asyncio.run(main([args.ex] if args.ex else [], args.symbol or ""))
