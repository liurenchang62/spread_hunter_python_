"""
查询 Binance + Bitget 所有持仓，找出单腿裸敞口并市价平仓。

用法：
    python -m tools.close_naked_positions          # 查询 + 平仓
    python -m tools.close_naked_positions --dry-run  # 只查看，不下单
"""

import argparse
import asyncio
import math
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; C = "\033[36m"; W = "\033[0m"; B = "\033[1m"


def _sym_base(sym: str) -> str:
    """把各所格式统一为大写去掉 USDT 后缀的 base，如 BSBUSDT → BSB"""
    s = sym.upper().replace("-USDT-SWAP", "").replace("_USDT", "").replace("USDT", "")
    return s.strip("-_")


async def _get_binance_positions(client) -> list[dict]:
    """返回 [{sym, side, size, entry}]，size>0 表示多头，<0 空头"""
    import aiohttp
    params, headers = client._sign({"timestamp": int(__import__("time").time() * 1000)})
    sess = await client._sess()
    async with sess.get(
        f"{client.base}/fapi/v2/positionRisk",
        params=params, headers=headers, ssl=False,
    ) as r:
        data = await r.json()
    result = []
    for p in data:
        amt = float(p.get("positionAmt", 0))
        if abs(amt) < 1e-9:
            continue
        result.append({
            "sym": p["symbol"],
            "base": _sym_base(p["symbol"]),
            "side": "long" if amt > 0 else "short",
            "size": abs(amt),
            "entry": float(p.get("entryPrice", 0)),
        })
    return result


async def _get_bitget_positions(client) -> list[dict]:
    """返回 [{sym, side, size, entry}]"""
    import time as _time
    path = "/api/v2/mix/position/all-position?productType=USDT-FUTURES&marginCoin=USDT"
    sess = await client._sess()
    async with sess.get(
        f"{client.base}{path}",
        headers=client._sign("GET", path),
        ssl=False,
    ) as r:
        data = await r.json()
    result = []
    if str(data.get("code", "")) != "00000":
        return result
    for p in (data.get("data") or []):
        size = float(p.get("total", 0))
        if size < 1e-9:
            continue
        side_raw = p.get("holdSide", "long")
        result.append({
            "sym": p["symbol"],
            "base": _sym_base(p["symbol"]),
            "side": side_raw,
            "size": size,
            "entry": float(p.get("openPriceAvg", 0)),
        })
    return result


async def _close_binance(client, sym: str, side: str, size: float):
    close_side = "SELL" if side == "long" else "BUY"
    qty_str = str(int(size)) if size == int(size) else str(size)
    req = {"symbol": sym.upper(), "side": close_side, "type": "MARKET",
           "quantity": qty_str, "reduceOnly": "true"}
    params, headers = client._sign(req)
    sess = await client._sess()
    async with sess.post(
        f"{client.base}/fapi/v1/order",
        params=params, headers=headers, ssl=False,
    ) as r:
        return await r.json()


async def _close_bitget(client, sym: str, side: str, size: float):
    close_side = "buy" if side == "short" else "sell"
    body = __import__("json").dumps({
        "symbol": sym, "productType": "USDT-FUTURES",
        "marginMode": "isolated", "marginCoin": "USDT",
        "size": str(int(size)) if size == int(size) else str(size),
        "side": close_side, "tradeSide": "close", "orderType": "market",
    })
    path = "/api/v2/mix/order/place-order"
    sess = await client._sess()
    async with sess.post(
        f"{client.base}{path}",
        headers=client._sign("POST", path, body),
        data=body, ssl=False,
    ) as r:
        return await r.json()


async def _main(dry_run: bool):
    from trader.exchange_client import BinanceClient, BitgetClient
    from clients.api_keys_live import get_live_keys

    bn = BinanceClient(live=True, keys=get_live_keys("binance"))
    bg = BitgetClient(live=True,  keys=get_live_keys("bitget"))

    print(f"\n{C}{B}{'═'*60}{W}")
    print(f"{C}{B}  单腿裸敞口检查{'  [DRY RUN]' if dry_run else ''}{W}")
    print(f"{C}{B}{'═'*60}{W}\n")

    try:
        try:
            bn_pos, bg_pos = await asyncio.gather(
                _get_binance_positions(bn),
                _get_bitget_positions(bg),
            )
        except Exception as e:
            print(f"{R}查询失败: {e}{W}")
            return

        bn_map = {p["base"]: p for p in bn_pos}
        bg_map = {p["base"]: p for p in bg_pos}

        all_bases = set(bn_map) | set(bg_map)

        print(f"  {'Base':<12} {'Binance':^20} {'Bitget':^20} {'状态'}")
        print(f"  {'-'*12} {'-'*20} {'-'*20} {'-'*10}")

        naked = []
        for base in sorted(all_bases):
            bn_p = bn_map.get(base)
            bg_p = bg_map.get(base)
            bn_s = f"{bn_p['side']} {bn_p['size']}" if bn_p else "—"
            bg_s = f"{bg_p['side']} {bg_p['size']}" if bg_p else "—"

            if bn_p and bg_p:
                # 检查数量是否匹配（偏差 >20% 视为不平衡）
                ratio = bn_p["size"] / bg_p["size"] if bg_p["size"] > 0 else 999
                if ratio < 0.8 or ratio > 1.2:
                    status = f"{Y}⚠ 数量不匹配 bn={bn_p['size']} bg={bg_p['size']}{W}"
                else:
                    status = f"{G}已对冲{W}"
            elif bn_p:
                status = f"{R}裸敞口(Binance){W}"
                naked.append(("binance", bn_p))
            elif bg_p:
                status = f"{R}裸敞口(Bitget){W}"
                naked.append(("bitget", bg_p))

            print(f"  {base:<12} {bn_s:^20} {bg_s:^20} {status}")

        if not naked:
            print(f"\n  {G}无裸敞口，无需处理。{W}\n")
            return

        print(f"\n  共发现 {len(naked)} 笔裸敞口\n")

        if dry_run:
            print(f"  {Y}[DRY RUN] 以上仓位将被市价平仓，实际未执行。{W}\n")
            return

        for ex, pos in naked:
            sym  = pos["sym"]
            side = pos["side"]
            size = pos["size"]
            print(f"  平仓 {ex} {sym} {side} size={size} ...", end=" ", flush=True)
            try:
                if ex == "binance":
                    resp = await _close_binance(bn, sym, side, size)
                else:
                    resp = await _close_bitget(bg, sym, side, size)
                code = resp.get("code", resp.get("status", "?"))
                if str(code) in ("00000", "200") or resp.get("orderId"):
                    print(f"{G}成功 {resp}{W}")
                else:
                    print(f"{R}失败 {resp}{W}")
            except Exception as e:
                print(f"{R}异常: {e}{W}")
    finally:
        await asyncio.gather(bn.close(), bg.close(), return_exceptions=True)
    print()


def main():
    ap = argparse.ArgumentParser(description="平仓单腿裸敞口")
    ap.add_argument("--dry-run", action="store_true", help="只查看，不下单")
    args = ap.parse_args()
    asyncio.run(_main(args.dry_run))


if __name__ == "__main__":
    main()
