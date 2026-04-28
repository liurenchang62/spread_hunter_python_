"""
全账户余额扫描——查遍各交易所所有钱包类型。

用法：
    python -m tools.find_balance
"""

import asyncio
import hashlib
import hmac
import base64
import time
import sys
from pathlib import Path
from urllib.parse import urlencode

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _sign_binance(keys, params):
    params["timestamp"] = int(time.time() * 1000)
    qs  = urlencode(params)
    sig = hmac.new(keys["secret"].encode(), qs.encode(), hashlib.sha256).hexdigest()
    params["signature"] = sig
    return params, {"X-MBX-APIKEY": keys["key"]}


def _sign_okx(keys, method, path, body=""):
    ts  = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    sig = base64.b64encode(
        hmac.new(keys["secret"].encode(),
                 (ts + method.upper() + path + body).encode(),
                 hashlib.sha256).digest()
    ).decode()
    return {
        "OK-ACCESS-KEY": keys["key"], "OK-ACCESS-SIGN": sig,
        "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": keys["passphrase"],
    }


def _sign_gate(keys, method, path, query=""):
    ts        = str(int(time.time()))
    body_hash = hashlib.sha512(b"").hexdigest()
    msg       = f"{method.upper()}\n{path}\n{query}\n{body_hash}\n{ts}"
    sig       = hmac.new(keys["secret"].encode(), msg.encode(), hashlib.sha512).hexdigest()
    return {"KEY": keys["key"], "SIGN": sig, "Timestamp": ts}


def _sign_bitget(keys, method, path):
    ts  = str(int(time.time() * 1000))
    sig = base64.b64encode(
        hmac.new(keys["secret"].encode(),
                 (ts + method.upper() + path).encode(),
                 hashlib.sha256).digest()
    ).decode()
    return {
        "ACCESS-KEY": keys["key"], "ACCESS-SIGN": sig,
        "ACCESS-TIMESTAMP": ts, "ACCESS-PASSPHRASE": keys["passphrase"],
    }


async def scan_binance(keys):
    spot = "https://api.binance.com"
    fapi = "https://fapi.binance.com"
    px   = {}
    conn = aiohttp.TCPConnector(ssl=False)
    results = {}

    async with aiohttp.ClientSession(connector=conn) as sess:
        # 1. 现货账户
        try:
            p, h = _sign_binance(keys, {})
            async with sess.get(f"{spot}/api/v3/account", params=p, headers=h, **px) as r:
                d = await r.json()
            for b in (d.get("balances") or []):
                if b["asset"] == "USDT":
                    results["现货(api/v3)"] = f"free={b['free']}  locked={b['locked']}"
        except Exception as e:
            results["现货(api/v3)"] = f"错误: {e}"

        # 2. capital/config（原get_spot_balance用的接口）
        try:
            p, h = _sign_binance(keys, {})
            async with sess.get(f"{spot}/sapi/v1/capital/config/getall", params=p, headers=h, **px) as r:
                d = await r.json()
            if isinstance(d, list):
                for item in d:
                    if item.get("coin") == "USDT":
                        results["现货(capital/config)"] = f"free={item.get('free')}  locked={item.get('locked')}"
            else:
                results["现货(capital/config)"] = str(d)
        except Exception as e:
            results["现货(capital/config)"] = f"错误: {e}"

        # 3. USDT-M 合约钱包
        try:
            p, h = _sign_binance(keys, {})
            async with sess.get(f"{fapi}/fapi/v2/balance", params=p, headers=h, **px) as r:
                d = await r.json()
            if isinstance(d, list):
                for item in d:
                    if item.get("asset") == "USDT":
                        results["期货(fapi/v2)"] = (
                            f"balance={item.get('balance')}  "
                            f"available={item.get('availableBalance')}  "
                            f"crossUnPnl={item.get('crossUnPnl')}"
                        )
            else:
                results["期货(fapi/v2)"] = str(d)
        except Exception as e:
            results["期货(fapi/v2)"] = f"错误: {e}"

        # 4. 资金账户（Funding wallet）
        try:
            p, h = _sign_binance(keys, {"asset": "USDT"})
            async with sess.post(f"{spot}/sapi/v1/asset/get-funding-asset", params=p, headers=h, **px) as r:
                d = await r.json()
            if isinstance(d, list) and d:
                for item in d:
                    if item.get("asset") == "USDT":
                        results["资金账户(funding)"] = f"free={item.get('free')}  locked={item.get('locked')}  freeze={item.get('freeze')}"
            elif isinstance(d, list):
                results["资金账户(funding)"] = "0（空）"
            else:
                results["资金账户(funding)"] = str(d)
        except Exception as e:
            results["资金账户(funding)"] = f"错误: {e}"

        # 5. 持仓信息（合约）
        try:
            p, h = _sign_binance(keys, {})
            async with sess.get(f"{fapi}/fapi/v2/positionRisk", params=p, headers=h, **px) as r:
                d = await r.json()
            open_pos = [x for x in (d if isinstance(d, list) else []) if float(x.get("positionAmt", 0)) != 0]
            results["合约持仓"] = f"{len(open_pos)} 个持仓" if open_pos else "无持仓"
        except Exception as e:
            results["合约持仓"] = f"错误: {e}"

    return results


async def scan_okx(keys):
    base = "https://www.okx.com"
    px   = {}
    conn = aiohttp.TCPConnector(ssl=False)
    results = {}

    async with aiohttp.ClientSession(connector=conn) as sess:
        # 1. 交易账户（合约用）
        try:
            path = "/api/v5/account/balance?ccy=USDT"
            async with sess.get(f"{base}{path}", headers=_sign_okx(keys, "GET", path), **px) as r:
                d = await r.json()
            if d.get("code") == "0":
                for item in (d.get("data") or [{}])[0].get("details", []):
                    if item.get("ccy") == "USDT":
                        results["交易账户"] = f"availBal={item.get('availBal')}  cashBal={item.get('cashBal')}  upl={item.get('upl')}"
            else:
                results["交易账户"] = str(d)
        except Exception as e:
            results["交易账户"] = f"错误: {e}"

        # 2. 资金账户（funding account，充值到账处）
        try:
            path = "/api/v5/asset/balances?ccy=USDT"
            async with sess.get(f"{base}{path}", headers=_sign_okx(keys, "GET", path), **px) as r:
                d = await r.json()
            if d.get("code") == "0":
                items = d.get("data") or []
                if items:
                    results["资金账户(funding)"] = f"bal={items[0].get('bal')}  availBal={items[0].get('availBal')}"
                else:
                    results["资金账户(funding)"] = "0（空）"
            else:
                results["资金账户(funding)"] = str(d)
        except Exception as e:
            results["资金账户(funding)"] = f"错误: {e}"

        # 3. 持仓
        try:
            path = "/api/v5/account/positions?instType=SWAP"
            async with sess.get(f"{base}{path}", headers=_sign_okx(keys, "GET", path), **px) as r:
                d = await r.json()
            open_pos = [x for x in (d.get("data") or []) if float(x.get("pos", 0)) != 0]
            results["合约持仓"] = f"{len(open_pos)} 个持仓" if open_pos else "无持仓"
        except Exception as e:
            results["合约持仓"] = f"错误: {e}"

    return results


async def scan_gate(keys):
    base = "https://api.gateio.ws"
    px   = {}
    conn = aiohttp.TCPConnector(ssl=False)
    results = {}

    async with aiohttp.ClientSession(connector=conn) as sess:
        # 1. 现货账户
        try:
            path  = "/api/v4/spot/accounts"
            query = "currency=USDT"
            async with sess.get(f"{base}{path}?{query}", headers=_sign_gate(keys, "GET", path, query), **px) as r:
                d = await r.json()
            for item in (d if isinstance(d, list) else []):
                if item.get("currency") == "USDT":
                    results["现货"] = f"available={item.get('available')}  locked={item.get('locked')}"
        except Exception as e:
            results["现货"] = f"错误: {e}"

        # 2. 期货账户
        try:
            path = "/api/v4/futures/usdt/accounts"
            async with sess.get(f"{base}{path}", headers=_sign_gate(keys, "GET", path), **px) as r:
                d = await r.json()
            if isinstance(d, dict):
                results["期货"] = f"available={d.get('available')}  total={d.get('total')}  unrealised_pnl={d.get('unrealised_pnl')}"
        except Exception as e:
            results["期货"] = f"错误: {e}"

    return results


async def scan_bitget(keys):
    base = "https://api.bitget.com"
    px   = {}
    conn = aiohttp.TCPConnector(ssl=False)
    results = {}

    async with aiohttp.ClientSession(connector=conn) as sess:
        # 1. 现货账户
        try:
            path = "/api/v2/spot/account/assets?coin=USDT"
            async with sess.get(f"{base}{path}", headers=_sign_bitget(keys, "GET", path), **px) as r:
                d = await r.json()
            for item in (d.get("data") or []):
                if item.get("coin") == "USDT":
                    results["现货"] = f"available={item.get('available')}  frozen={item.get('frozen')}"
        except Exception as e:
            results["现货"] = f"错误: {e}"

        # 2. 期货账户
        try:
            path = "/api/v2/mix/account/accounts?productType=USDT-FUTURES"
            ts  = str(int(time.time() * 1000))
            sig = base64.b64encode(
                hmac.new(keys["secret"].encode(),
                         (ts + "GET" + path).encode(), hashlib.sha256).digest()
            ).decode()
            h = {"ACCESS-KEY": keys["key"], "ACCESS-SIGN": sig,
                 "ACCESS-TIMESTAMP": ts, "ACCESS-PASSPHRASE": keys["passphrase"]}
            async with sess.get(f"{base}{path}", headers=h, **px) as r:
                d = await r.json()
            for item in (d.get("data") or []):
                if item.get("marginCoin") == "USDT":
                    results["期货(USDT-FUTURES)"] = f"available={item.get('available')}  equity={item.get('equity')}"
        except Exception as e:
            results["期货(USDT-FUTURES)"] = f"错误: {e}"

    return results


async def _main():
    from clients.api_keys_live import get_live_keys

    C = "\033[36m"; W = "\033[0m"; B = "\033[1m"; G = "\033[32m"; R = "\033[31m"

    scanners = {
        "binance": scan_binance,
        "okx":     scan_okx,
        "gate":    scan_gate,
        "bitget":  scan_bitget,
    }

    print(f"\n{C}{'═'*60}{W}")
    print(f"{C}{B}  全账户余额扫描{W}")
    print(f"{C}{'═'*60}{W}\n")

    for ex, scanner in scanners.items():
        keys = get_live_keys(ex)
        if not keys or not keys.get("key"):
            print(f"  {ex}: 未配置API Key\n")
            continue
        print(f"{C}{B}── {ex.upper()} ──{W}")
        try:
            results = await scanner(keys)
            for label, val in results.items():
                # 高亮非零余额
                has_money = False
                for tok in str(val).split():
                    if "=" in tok:
                        try:
                            v = float(tok.split("=")[1])
                            if v > 0.01:
                                has_money = True
                        except Exception:
                            pass
                color = G if has_money else W
                print(f"  {color}{label:<22}{W}  {val}")
        except Exception as e:
            print(f"  {R}扫描失败: {e}{W}")
        print()

    print(f"{C}{'═'*60}{W}\n")


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()
