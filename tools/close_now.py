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
        # 查询实际持仓
        path = "/api/v2/mix/position/all-position?productType=USDT-FUTURES&marginCoin=USDT"
        sess = await bg._sess()
        async with sess.get(f"{bg.base}{path}", headers=bg._sign("GET", path), ssl=False) as r:
            raw = await r.json()

        positions = [p for p in (raw.get("data") or []) if float(p.get("total", 0)) > 0]
        if not positions:
            print("Bitget 无持仓")
            return

        print("=== Bitget 持仓 ===")
        for p in positions:
            print(f"  {p['symbol']}  {p['holdSide']}  total={p['total']}")

        # 用 place_order reduce_only=True 平仓（走已验证的代码路径）
        from trader.market_info import MarketInfo
        mi = MarketInfo()
        await mi.refresh_all(list(bg._sess.__self__ if hasattr(bg._sess, '__self__') else []))

        for p in positions:
            sym = p["symbol"]
            hold_side = p["holdSide"]   # "long" or "short"
            size = float(p["total"])
            close_side = "sell" if hold_side == "long" else "buy"

            print(f"平仓 {sym} {hold_side} size={size} side={close_side} ...", end=" ", flush=True)
            try:
                # 直接构造关单请求（与 exchange_client place_order 内部逻辑一致）
                import json, math
                qty = size  # 已是整数coins
                size_str = str(int(qty)) if qty == int(qty) else str(qty)

                for product_type, use_pap, margin_coin in [
                    ("USDT-FUTURES", True, "USDT"),
                    ("SUSDT-FUTURES", False, "SUSDT"),
                ]:
                    body_d = {
                        "symbol": sym, "productType": product_type,
                        "marginMode": "isolated", "marginCoin": margin_coin,
                        "size": size_str, "side": close_side,
                        "tradeSide": "close", "orderType": "market",
                    }
                    body = json.dumps(body_d)
                    path2 = "/api/v2/mix/order/place-order"
                    sess2 = await bg._sess()
                    async with sess2.post(
                        f"{bg.base}{path2}",
                        headers=bg._sign("POST", path2, body, use_pap=use_pap),
                        data=body, ssl=False,
                    ) as r2:
                        data = await r2.json()
                    print(f"[{product_type}] {data}", end=" ")
                    if str(data.get("code", "")) == "00000":
                        print("✓")
                        break
                else:
                    print("✗ 两种模式都失败")
            except Exception as e:
                print(f"异常: {e}")
    finally:
        await bg.close()

asyncio.run(main())
