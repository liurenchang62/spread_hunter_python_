"""临时脚本：平仓 BSB 和 UB 两腿，用完即删"""
import asyncio, sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

async def main():
    from trader.exchange_client import BinanceClient, BitgetClient
    from clients.api_keys_live import get_live_keys

    bn = BinanceClient(live=True, keys=get_live_keys("binance"))
    bg = BitgetClient(live=True,  keys=get_live_keys("bitget"))

    # Binance 平仓：空头用 BUY reduceOnly
    async def bn_close(sym, qty):
        import time
        req = {"symbol": sym, "side": "BUY", "type": "MARKET",
               "quantity": str(qty), "reduceOnly": "true"}
        params, headers = bn._sign(req)
        sess = await bn._sess()
        async with sess.post(f"{bn.base}/fapi/v1/order",
                             params=params, headers=headers, ssl=False) as r:
            return await r.json()

    # Bitget 平仓：多头用 sell close
    async def bg_close(sym, qty):
        import json
        body = json.dumps({"symbol": sym, "productType": "USDT-FUTURES",
                           "marginMode": "isolated", "marginCoin": "USDT",
                           "size": str(int(qty)) if qty == int(qty) else str(qty), "side": "sell",
                           "tradeSide": "close", "orderType": "market"})
        path = "/api/v2/mix/order/place-order"
        sess = await bg._sess()
        async with sess.post(f"{bg.base}{path}",
                             headers=bg._sign("POST", path, body),
                             data=body, ssl=False) as r:
            return await r.json()

    # 先查询 Bitget 实际持仓，打印原始数据
    path = "/api/v2/mix/position/all-position?productType=USDT-FUTURES&marginCoin=USDT"
    sess = await bg._sess()
    async with sess.get(f"{bg.base}{path}", headers=bg._sign("GET", path), ssl=False) as r:
        raw = await r.json()
    print("=== Bitget 原始持仓 ===")
    for p in (raw.get("data") or []):
        print(f"  symbol={p.get('symbol')}  holdSide={p.get('holdSide')}  total={p.get('total')}  marginMode={p.get('marginMode')}")

    # 用实际 symbol 平仓
    to_close = [(p.get("symbol"), p.get("holdSide"), float(p.get("total", 0)))
                for p in (raw.get("data") or [])
                if float(p.get("total", 0)) > 0]

    for sym, side, size in to_close:
        close_side = "buy" if side == "short" else "sell"
        print(f"平仓 Bitget {sym} {side} size={size} ...", end=" ", flush=True)
        try:
            r = await bg_close(sym, size)
            ok = r.get("data") or str(r.get("code","")) == "00000"
            print("✓" if ok else f"✗ {r}")
        except Exception as e:
            print(f"异常: {e}")

    await asyncio.gather(bn.close(), bg.close(), return_exceptions=True)

asyncio.run(main())
