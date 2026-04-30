"""临时诊断+平仓脚本，用完即删"""
import asyncio, sys, json
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

async def query_positions(bg):
    path = "/api/v2/mix/position/all-position?productType=USDT-FUTURES&marginCoin=USDT"
    sess = await bg._sess()
    async with sess.get(f"{bg.base}{path}", headers=bg._sign("GET", path), ssl=False) as r:
        data = await r.json()
    return [p for p in (data.get("data") or []) if float(p.get("total", 0)) > 0]

async def close_position(bg, p):
    sym = p["symbol"]
    hold_side = p["holdSide"]
    size = float(p["total"])
    size_str = str(int(size)) if size == int(size) else str(size)
    close_side = "sell" if hold_side == "long" else "buy"
    body_d = {"symbol": sym, "productType": "USDT-FUTURES",
              "marginMode": p.get("marginMode", "isolated"), "marginCoin": "USDT",
              "size": size_str, "side": close_side,
              "tradeSide": "close", "orderType": "market"}
    body = json.dumps(body_d)
    path = "/api/v2/mix/order/place-order"
    sess = await bg._sess()
    async with sess.post(f"{bg.base}{path}",
                         headers=bg._sign("POST", path, body),
                         data=body, ssl=False) as r:
        return await r.json()

async def main():
    from trader.exchange_client import BitgetClient
    from clients.api_keys_live import get_live_keys
    keys = get_live_keys("bitget")

    bg_live = BitgetClient(live=True,  keys=keys)
    bg_pap  = BitgetClient(live=False, keys=keys)

    # 先查期货账户详情
    path = "/api/v2/mix/account/accounts?productType=USDT-FUTURES"
    sess = await bg_live._sess()
    async with sess.get(f"{bg_live.base}{path}",
                        headers=bg_live._sign("GET", path), ssl=False) as r:
        acc = await r.json()
    print("=== Bitget 期货账户 ===")
    for a in (acc.get("data") or []):
        print(f"  available={a.get('available')} frozen={a.get('frozen')} "
              f"unrealizedPL={a.get('unrealizedPL')} equity={a.get('equity')} "
              f"isolatedFrozen={a.get('isolatedFrozen')}")

    try:
        live_pos = await query_positions(bg_live)
        pap_pos  = await query_positions(bg_pap)

        print(f"=== LIVE 持仓 ({len(live_pos)}) ===")
        for p in live_pos:
            print(f"  {p['symbol']} {p['holdSide']} total={p['total']} marginMode={p.get('marginMode')}")

        print(f"\n=== PAP 持仓 ({len(pap_pos)}) ===")
        for p in pap_pos:
            print(f"  {p['symbol']} {p['holdSide']} total={p['total']} marginMode={p.get('marginMode')}")

        # 判断在哪个环境，用对应客户端平仓
        to_close = []
        if pap_pos:
            print("\n→ 发现 PAP 仓位，用 PAP 模式平仓")
            for p in pap_pos:
                to_close.append((bg_pap, p))
        if live_pos:
            print("\n→ 发现 LIVE 仓位，用 LIVE 模式平仓")
            for p in live_pos:
                to_close.append((bg_live, p))

        # 查账户持仓模式
        print("\n=== 账户模式 ===")
        path_mode = "/api/v2/mix/account/accounts?productType=USDT-FUTURES"
        sess = await bg_live._sess()
        async with sess.get(f"{bg_live.base}{path_mode}",
                            headers=bg_live._sign("GET", path_mode), ssl=False) as r:
            mode_data = await r.json()
        for acc in (mode_data.get("data") or []):
            print(f"  marginCoin={acc.get('marginCoin')} posMode={acc.get('posMode')} "
                  f"autoMargin={acc.get('autoMargin')} available={acc.get('available')}")

        # 查未成交订单
        print("\n=== 未成交订单 ===")
        for bg, p in to_close:
            sym = p["symbol"]
            path = f"/api/v2/mix/order/orders-pending?productType=USDT-FUTURES&symbol={sym}"
            sess = await bg._sess()
            async with sess.get(f"{bg.base}{path}", headers=bg._sign("GET", path), ssl=False) as r:
                info = await r.json()
            orders = (info.get("data") or {}).get("entrustedList") or []
            if orders:
                for o in orders:
                    print(f"  {sym}: orderId={o.get('orderId')} side={o.get('side')} tradeSide={o.get('tradeSide')} size={o.get('size')} status={o.get('status')}")
            else:
                print(f"  {sym}: 无未成交订单")

        # 查合约规格（步长/最小下单量）
        print("\n=== 合约规格 ===")
        for bg, p in to_close:
            sym = p["symbol"]
            path = f"/api/v2/mix/market/contracts?productType=USDT-FUTURES&symbol={sym}"
            sess = await bg._sess()
            async with sess.get(f"{bg.base}{path}", ssl=False) as r:
                info = await r.json()
            for c in (info.get("data") or []):
                print(f"  {sym}: sizeMultiplier={c.get('sizeMultiplier')} minTradeNum={c.get('minTradeNum')} volumePlace={c.get('volumePlace')} raw={c}")

        for bg, p in to_close:
            mode = "PAP" if not bg.live else "LIVE"
            print(f"平仓 [{mode}] {p['symbol']} {p['holdSide']} ...", end=" ", flush=True)
            res = await close_position(bg, p)
            print(f"{'✓' if str(res.get('code',''))=='00000' else '✗'} {res}")

    finally:
        await asyncio.gather(bg_live.close(), bg_pap.close(), return_exceptions=True)

asyncio.run(main())
