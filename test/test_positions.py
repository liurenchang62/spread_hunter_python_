"""
测试持仓查询（get_positions）与挂单查询（get_open_orders）。

用法：
    python -m test.test_positions
    python -m test.test_positions --ex okx
    python -m test.test_positions --symbol BTCUSDT   # 只查某合约
"""
import argparse
import asyncio

from test._common import *


async def _show_positions(name: str, client, symbol: str):
    print(f"\n  [{name.upper()}]")

    # ── 持仓查询
    try:
        positions = await client.get_positions(symbol=symbol)
        if positions:
            ok(f"活跃持仓 {len(positions)} 笔:")
            for p in positions:
                # 兼容各所字段名
                sym   = p.get("symbol") or p.get("instId") or p.get("contract") or "?"
                size  = p.get("positionAmt") or p.get("pos") or p.get("size") or p.get("total") or "?"
                side  = p.get("positionSide") or p.get("posSide") or ("long" if float(size or 0) > 0 else "short")
                entry = p.get("entryPrice") or p.get("avgPx") or p.get("entry_price") or p.get("openPriceAvg") or "?"
                upnl  = p.get("unrealizedProfit") or p.get("upl") or p.get("unrealised_pnl") or p.get("unrealizedPL") or "?"
                # 确保所有值转为字符串，避免格式化错误
                info(f"  {str(sym):20s} side={str(side):5s} size={str(size):10s} entry={str(entry):12s} upnl={upnl}")
        else:
            ok("无活跃持仓")
    except Exception as e:
        fail(f"持仓查询失败: {e}")

    # ── 挂单查询
    try:
        orders = await client.get_open_orders(symbol=symbol)
        if orders:
            ok(f"挂单 {len(orders)} 笔:")
            for o in orders[:5]:
                oid  = o.get("orderId") or o.get("ordId") or o.get("id") or "?"
                sym  = o.get("symbol") or o.get("instId") or o.get("contract") or "?"
                side = o.get("side") or "?"
                px   = o.get("price") or o.get("px") or "?"
                qty  = o.get("origQty") or o.get("sz") or o.get("size") or "?"
                info(f"  id={oid} {sym} {side} price={px} qty={qty}")
        else:
            ok("无挂单")
    except Exception as e:
        fail(f"挂单查询失败: {e}")


async def main(targets: list[str], symbol: str):
    clients = load_clients()
    section("持仓 & 挂单查询测试")

    for name, client in clients.items():
        if targets and name not in targets:
            continue
        sym = symbol or TEST_SYMBOL.get(name, "")
        try:
            await _show_positions(name, client, sym)
        except Exception as e:
            fail(f"{name} 查询异常: {e}")

    for c in clients.values():
        await c.close()
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="持仓 & 挂单查询测试")
    parser.add_argument("--ex",     help="只查某交易所")
    parser.add_argument("--symbol", help="只查某合约（不填则查全部）")
    args = parser.parse_args()
    targets = [args.ex] if args.ex else []
    asyncio.run(main(targets, args.symbol or ""))
