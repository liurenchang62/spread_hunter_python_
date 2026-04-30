"""临时脚本：平仓 Bitget 裸敞口，用完即删"""
import asyncio, sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

async def main():
    from trader.exchange_client import BitgetClient
    from clients.api_keys_live import get_live_keys

    bg = BitgetClient(live=True, keys=get_live_keys("bitget"))

    try:
        # 查询持仓
        path = "/api/v2/mix/position/all-position?productType=USDT-FUTURES&marginCoin=USDT"
        sess = await bg._sess()
        async with sess.get(f"{bg.base}{path}", headers=bg._sign("GET", path), ssl=False) as r:
            raw = await r.json()

        positions = [p for p in (raw.get("data") or []) if float(p.get("total", 0)) > 0]
        if not positions:
            print("Bitget 无持仓")
            return

        for p in positions:
            sym       = p["symbol"]
            hold_side = p["holdSide"]
            size      = float(p["total"])
            close_side = "sell" if hold_side == "long" else "buy"
            # 取当前市价作为 ref_price
            ref_price  = float(p.get("openPriceAvg") or p.get("markPrice") or 1.0)

            print(f"平仓 {sym} {hold_side} size={size} ...", end=" ", flush=True)
            # 不用 tradeSide:close，直接 market sell（one-way 模式会净仓）
            import json
            size_str = str(int(size)) if size == int(size) else str(size)
            body_d = {"symbol": sym, "productType": "USDT-FUTURES",
                      "marginCoin": "USDT", "size": size_str,
                      "side": close_side, "tradeSide": "close", "orderType": "market"}
            body = json.dumps(body_d)
            path2 = "/api/v2/mix/order/place-order"
            sess2 = await bg._sess()
            async with sess2.post(f"{bg.base}{path2}",
                                  headers=bg._sign("POST", path2, body),
                                  data=body, ssl=False) as r2:
                data = await r2.json()
            print(f"{'✓' if str(data.get('code',''))=='00000' else '✗'} {data}")
    finally:
        await bg.close()

asyncio.run(main())
