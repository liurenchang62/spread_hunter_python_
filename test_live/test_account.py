"""
实盘账户信息全面检查（只读，不涉及交易）。

检查项：
  - 合约账户可用余额（futures balance）
  - 现货/资金账户可用余额（spot/funding balance）
  - 当前持仓（open positions）
  - 当前挂单（open orders）

用法：
    python -m test_live.test_account
    python -m test_live.test_account --ex gate
"""

import argparse
import asyncio

from test_live._common import *


async def _check_one(name: str, client):
    section(f"{name.upper()} — 账户检查")

    # ── 合约余额 ──────────────────────────────────────────────────────────────
    print(f"\n  [合约余额]")
    try:
        bal = await client.get_balance()
        if bal > 0:
            ok(f"合约可用余额: {bal:.4f} USDT")
        else:
            warn(f"合约可用余额: {bal:.4f} USDT（为 0，请检查是否已充值）")
    except Exception as e:
        fail(f"合约余额查询失败: {e}")

    # ── 现货/资金余额 ─────────────────────────────────────────────────────────
    print(f"\n  [现货/资金余额]")
    try:
        spot = await client.get_spot_balance()
        if spot > 0:
            ok(f"现货/资金可用余额: {spot:.4f} USDT")
        else:
            warn(f"现货/资金可用余额: {spot:.4f} USDT（为 0）")
    except Exception as e:
        fail(f"现货余额查询失败: {e}")

    # ── 持仓 ──────────────────────────────────────────────────────────────────
    print(f"\n  [当前持仓]")
    try:
        positions = await client.get_positions()
        if not positions:
            ok("无持仓")
        else:
            warn(f"有 {len(positions)} 笔持仓：")
            for p in positions[:5]:
                # 各所字段名不统一，尽量兼容
                sym  = p.get("symbol") or p.get("instId") or p.get("contract") or p.get("symbol", "?")
                size = (p.get("positionAmt") or p.get("pos") or
                        p.get("size") or p.get("total") or "?")
                upnl = (p.get("unrealizedProfit") or p.get("upl") or
                        p.get("unrealised_pnl") or p.get("unrealizedPL") or "?")
                info(f"  {sym}  size={size}  unPnL={upnl}")
            if len(positions) > 5:
                info(f"  ... 共 {len(positions)} 笔（只显示前5笔）")
    except Exception as e:
        fail(f"持仓查询失败: {e}")

    # ── 挂单 ──────────────────────────────────────────────────────────────────
    print(f"\n  [当前挂单]")
    try:
        orders = await client.get_open_orders()
        if not orders:
            ok("无挂单")
        else:
            warn(f"有 {len(orders)} 笔挂单：")
            for o in orders[:5]:
                oid  = o.get("orderId") or o.get("ordId") or o.get("id") or "?"
                sym  = o.get("symbol") or o.get("instId") or o.get("contract") or "?"
                side = o.get("side") or o.get("posSide") or "?"
                px   = o.get("price") or o.get("px") or "?"
                sz   = o.get("origQty") or o.get("sz") or o.get("size") or "?"
                info(f"  id={oid}  {sym}  {side}  px={px}  sz={sz}")
            if len(orders) > 5:
                info(f"  ... 共 {len(orders)} 笔（只显示前5笔）")
    except Exception as e:
        fail(f"挂单查询失败: {e}")


async def main(targets: list[str]):
    clients = load_live_clients()
    if not clients:
        return

    print(f"\n{R}⚠️  实盘模式（主网 API Key）{W}")

    for name, client in clients.items():
        if targets and name not in targets:
            continue
        try:
            await _check_one(name, client)
        except Exception as e:
            fail(f"{name} 检查异常: {e}")

    for c in clients.values():
        await c.close()
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="实盘账户信息检查")
    parser.add_argument("--ex", help="只测某交易所: binance/okx/gate/bitget")
    args = parser.parse_args()
    asyncio.run(main([args.ex] if args.ex else []))
