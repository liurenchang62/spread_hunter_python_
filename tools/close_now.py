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
                           "size": str(qty), "side": "sell",
                           "tradeSide": "close", "orderType": "market"})
        path = "/api/v2/mix/order/place-order"
        sess = await bg._sess()
        async with sess.post(f"{bg.base}{path}",
                             headers=bg._sign("POST", path, body),
                             data=body, ssl=False) as r:
            return await r.json()

    jobs = [
        ("Binance", "BSBUSDT",  7,  bn_close),
        ("Binance", "UBUSDT",  96,  bn_close),
        ("Bitget",  "BSBUSDT", 32,  bg_close),
        ("Bitget",  "UBUSDT",  96,  bg_close),
    ]

    for ex, sym, qty, fn in jobs:
        print(f"平仓 {ex} {sym} qty={qty} ...", end=" ", flush=True)
        try:
            r = await fn(sym, qty)
            ok = r.get("orderId") or str(r.get("code","")) == "00000"
            print("✓" if ok else f"✗ {r}")
        except Exception as e:
            print(f"异常: {e}")

    await asyncio.gather(bn.close(), bg.close(), return_exceptions=True)

asyncio.run(main())
