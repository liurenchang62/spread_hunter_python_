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
            res = await bg.place_order(
                symbol=sym, side=close_side,
                target_qty=size, ref_price=ref_price,
                symbol_info=None, reduce_only=True,
            )
            if res.success:
                print(f"✓ orderId={res.order_id} fill={res.fill_price}")
            else:
                print(f"✗ {res.error}")
    finally:
        await bg.close()

asyncio.run(main())
