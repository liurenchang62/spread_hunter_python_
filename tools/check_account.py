"""
各交易所现金余额 + 当前持仓合约查看工具。

用法：
    python -m tools.check_account          # 查询全部 4 所
    python -m tools.check_account --ex gate okx
"""

import argparse
import asyncio
import sys

import aiohttp

EXCHANGES = ["binance", "okx", "gate", "bitget"]


# ═════════════════════════════════════════════════════════════════════════════
#  各所余额查询（复用 exchange_client 已有方法）
# ═════════════════════════════════════════════════════════════════════════════

async def _query_exchange(ex: str, keys: dict) -> dict:
    """返回 {balance, total, positions}"""
    from trader.exchange_client import (
        BinanceClient, OKXClient, GateClient, BitgetClient
    )
    cls_map = {
        "binance": BinanceClient,
        "okx":     OKXClient,
        "gate":    GateClient,
        "bitget":  BitgetClient,
    }
    client = cls_map[ex](live=True, keys=keys)
    try:
        balance, total, spot, positions = await asyncio.gather(
            client.get_balance(),
            client.get_total_balance(),
            client.get_spot_balance(),
            client.get_positions(),
            return_exceptions=True,
        )
        return {
            "balance":   balance   if isinstance(balance,   float) else 0.0,
            "total":     total     if isinstance(total,     float) else 0.0,
            "spot":      spot      if isinstance(spot,      float) else 0.0,
            "positions": positions if isinstance(positions, list)  else [],
            "error":     None,
        }
    except Exception as e:
        return {"balance": 0.0, "total": 0.0, "positions": [], "error": str(e)}
    finally:
        await client.close()


# ═════════════════════════════════════════════════════════════════════════════
#  显示
# ═════════════════════════════════════════════════════════════════════════════

def _fmt(v: float) -> str:
    return f"{v:>10.2f}"


def _print_results(results: dict[str, dict]):
    # ── 余额汇总表 ────────────────────────────────────────────────────────
    print("\n╔══ 余额概览（合约账户） ══════════════════════════════════════════════╗")
    print(f"  {'交易所':<10} {'合约可用':>10} {'合约权益':>10} {'占用保证金':>12} {'使用率':>8} {'现货(待划)':>12}")
    print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*12} {'-'*8} {'-'*12}")
    total_avail = total_equity = total_spot = 0.0
    for ex, r in results.items():
        if r["error"]:
            print(f"  {ex:<10} {'[查询失败]':>10}  {r['error'][:30]}")
            continue
        avail  = r["balance"]
        equity = r["total"]
        spot   = r.get("spot", 0.0)
        locked = max(0.0, equity - avail)
        usage  = locked / equity * 100 if equity > 0 else 0.0
        spot_flag = f" ⚠" if spot > 0.5 else ""
        total_avail  += avail
        total_equity += equity
        total_spot   += spot
        print(f"  {ex:<10} {_fmt(avail)} {_fmt(equity)} {_fmt(locked)} {usage:>7.1f}% {_fmt(spot)}{spot_flag}")
    print(f"  {'合计':<10} {_fmt(total_avail)} {_fmt(total_equity)} {'':>12} {'':>8} {_fmt(total_spot)}")
    if total_spot > 0.5:
        print(f"\n  ⚠  现货账户有 {total_spot:.2f}U 未划入期货，运行 python -m tools.sweep_to_futures 一键划转")
    print("╚═══════════════════════════════════════════════════════════════════╝")

    # ── 各所持仓 ──────────────────────────────────────────────────────────
    any_pos = False
    for ex, r in results.items():
        if r["error"] or not r["positions"]:
            continue
        if not any_pos:
            print("\n╔══ 当前持仓 ═════════════════════════════════════════════════════╗")
            any_pos = True

        print(f"\n  ── {ex.upper()} ──")
        for p in r["positions"]:
            _print_position(ex, p)

    if not any_pos:
        print("\n  （各所均无开放持仓）")
    else:
        print("╚═══════════════════════════════════════════════════════════════╝")
    print()


def _print_position(ex: str, p: dict):
    """按各所字段结构解析并打印持仓行。"""
    if ex == "binance":
        sym    = p.get("symbol", "")
        side   = "多" if float(p.get("positionAmt", 0)) > 0 else "空"
        qty    = abs(float(p.get("positionAmt", 0)))
        entry  = float(p.get("entryPrice", 0))
        upnl   = float(p.get("unrealizedProfit", 0))
        lev    = p.get("leverage", "?")
        margin = float(p.get("isolatedMargin", p.get("initialMargin", 0)))
    elif ex == "okx":
        sym    = p.get("instId", "")
        pos_sz = float(p.get("pos", 0))
        side   = "多" if pos_sz > 0 else "空"
        qty    = abs(pos_sz)
        entry  = float(p.get("avgPx", 0) or 0)
        upnl   = float(p.get("upl", 0) or 0)
        lev    = p.get("lever", "?")
        margin = float(p.get("margin", 0) or 0)
    elif ex == "gate":
        sym    = p.get("contract", "")
        sz     = int(p.get("size", 0))
        side   = "多" if sz > 0 else "空"
        qty    = abs(sz)
        entry  = float(p.get("entry_price", 0) or 0)
        upnl   = float(p.get("unrealised_pnl", 0) or 0)
        lev    = p.get("leverage", "?")
        margin = float(p.get("margin", 0) or 0)
    elif ex == "bitget":
        sym    = p.get("symbol", "")
        hold   = p.get("holdSide", "long")
        side   = "多" if hold == "long" else "空"
        qty    = float(p.get("total", p.get("available", 0)) or 0)
        entry  = float(p.get("openPriceAvg", p.get("averageOpenPrice", 0)) or 0)
        upnl   = float(p.get("unrealizedPL", p.get("unrealizedPnl", 0)) or 0)
        lev    = p.get("leverage", "?")
        margin = float(p.get("margin", 0) or 0)
    else:
        print(f"    {p}")
        return

    upnl_str = f"{upnl:+.4f}" if upnl != 0 else "   --  "
    print(
        f"    {sym:<22} {side}  qty={qty:<10}  "
        f"entry={entry:<10.4f}  uPnL={upnl_str}  "
        f"margin={margin:.2f}  lev={lev}x"
    )


# ═════════════════════════════════════════════════════════════════════════════
#  主流程
# ═════════════════════════════════════════════════════════════════════════════

async def _main(exchanges: list[str]):
    from clients.api_keys_live import get_live_keys

    tasks = {}
    for ex in exchanges:
        keys = get_live_keys(ex)
        if not keys or not keys.get("key"):
            print(f"[{ex}] 未配置实盘 API Key，跳过")
            continue
        tasks[ex] = _query_exchange(ex, keys)

    results_list = await asyncio.gather(*tasks.values(), return_exceptions=True)
    results: dict[str, dict] = {}
    for ex, r in zip(tasks.keys(), results_list):
        if isinstance(r, Exception):
            results[ex] = {"balance": 0.0, "total": 0.0, "positions": [], "error": str(r)}
        else:
            results[ex] = r

    _print_results(results)


def main():
    ap = argparse.ArgumentParser(description="查看各交易所余额和当前持仓")
    ap.add_argument("--ex", nargs="+", default=EXCHANGES, help="指定交易所（默认全部）")
    args = ap.parse_args()

    asyncio.run(_main(args.ex))


if __name__ == "__main__":
    main()
