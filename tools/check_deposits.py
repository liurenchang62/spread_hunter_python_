"""
查询各交易所链上充值/提现记录（USDT），用于追踪资金流向。

用法：
    python -m tools.check_deposits            # 最近 30 天
    python -m tools.check_deposits --days 7
    python -m tools.check_deposits --ex gate  # 只查某所
"""

import argparse
import asyncio
import hashlib
import hmac
import base64
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _ms_to_str(ms: int) -> str:
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def _ts_to_str(ts: int) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def _now_ms() -> int:
    return int(time.time() * 1000)


# ═══════════════════════════════════════════════════════════════
#  Binance
# ═══════════════════════════════════════════════════════════════

async def _binance(keys: dict, start_ms: int, end_ms: int):
    spot = "https://api.binance.com"

    def _sign(params: dict):
        params["timestamp"] = int(time.time() * 1000)
        qs  = urlencode(params)
        sig = hmac.new(keys["secret"].encode(), qs.encode(), hashlib.sha256).hexdigest()
        params["signature"] = sig
        return params, {"X-MBX-APIKEY": keys["key"]}

    deposits    = []
    withdrawals = []

    conn = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=conn) as sess:
        # 充值记录
        p, h = _sign({"coin": "USDT", "startTime": start_ms, "endTime": end_ms, "limit": 100})
        async with sess.get(f"{spot}/sapi/v1/capital/deposit/hisrec", params=p, headers=h) as r:
            data = await r.json()
        if isinstance(data, list):
            for d in data:
                deposits.append({
                    "time":    _ms_to_str(int(d.get("insertTime", 0))),
                    "amount":  d.get("amount", ""),
                    "coin":    d.get("coin", ""),
                    "network": d.get("network", ""),
                    "status":  d.get("status", ""),   # 1=success
                    "txid":    d.get("txId", ""),
                    "address": d.get("address", ""),
                })
        else:
            deposits.append({"error": str(data)})

        # 提现记录
        p, h = _sign({"coin": "USDT", "startTime": start_ms, "endTime": end_ms, "limit": 100})
        async with sess.get(f"{spot}/sapi/v1/capital/withdraw/history", params=p, headers=h) as r:
            data = await r.json()
        if isinstance(data, list):
            for d in data:
                withdrawals.append({
                    "time":    _ms_to_str(int(d.get("applyTime", "0") or 0)),
                    "amount":  d.get("amount", ""),
                    "coin":    d.get("coin", ""),
                    "network": d.get("network", ""),
                    "status":  d.get("status", ""),   # 6=completed
                    "txid":    d.get("txId", ""),
                    "address": d.get("address", ""),
                    "fee":     d.get("transactionFee", ""),
                })
        else:
            withdrawals.append({"error": str(data)})

    return deposits, withdrawals


# ═══════════════════════════════════════════════════════════════
#  OKX
# ═══════════════════════════════════════════════════════════════

async def _okx(keys: dict, start_ms: int, end_ms: int):
    base = "https://www.okx.com"

    def _sign(method: str, path: str, body: str = "") -> dict:
        ts  = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        sig = base64.b64encode(
            hmac.new(keys["secret"].encode(),
                     (ts + method.upper() + path + body).encode(),
                     hashlib.sha256).digest()
        ).decode()
        return {
            "OK-ACCESS-KEY":        keys["key"],
            "OK-ACCESS-SIGN":       sig,
            "OK-ACCESS-TIMESTAMP":  ts,
            "OK-ACCESS-PASSPHRASE": keys["passphrase"],
            "Content-Type":         "application/json",
        }

    deposits    = []
    withdrawals = []

    conn = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=conn) as sess:
        # 充值记录（OKX 用秒时间戳）
        path = f"/api/v5/asset/deposit-history?ccy=USDT"
        async with sess.get(f"{base}{path}", headers=_sign("GET", path)) as r:
            data = await r.json()
        for d in (data.get("data") or []):
            ts_ms = int(d.get("ts", 0))
            if ts_ms and not (start_ms <= ts_ms <= end_ms):
                continue
            deposits.append({
                "time":    _ms_to_str(ts_ms),
                "amount":  d.get("amt", ""),
                "coin":    d.get("ccy", ""),
                "network": d.get("chain", ""),
                "status":  d.get("state", ""),  # 2=success
                "txid":    d.get("txId", ""),
                "address": d.get("to", ""),
            })

        # 提现记录
        path = f"/api/v5/asset/withdrawal-history?ccy=USDT"
        async with sess.get(f"{base}{path}", headers=_sign("GET", path)) as r:
            data = await r.json()
        for d in (data.get("data") or []):
            ts_ms = int(d.get("ts", 0))
            if ts_ms and not (start_ms <= ts_ms <= end_ms):
                continue
            withdrawals.append({
                "time":    _ms_to_str(ts_ms),
                "amount":  d.get("amt", ""),
                "coin":    d.get("ccy", ""),
                "network": d.get("chain", ""),
                "status":  d.get("state", ""),  # 2=success
                "txid":    d.get("txId", ""),
                "address": d.get("to", ""),
                "fee":     d.get("fee", ""),
            })

    return deposits, withdrawals


# ═══════════════════════════════════════════════════════════════
#  Gate
# ═══════════════════════════════════════════════════════════════

async def _gate(keys: dict, start_ms: int, end_ms: int):
    base = "https://api.gateio.ws"
    start_ts = start_ms // 1000
    end_ts   = end_ms   // 1000

    def _sign(method: str, path: str, query: str = "", body: str = "") -> dict:
        ts        = str(int(time.time()))
        body_hash = hashlib.sha512(body.encode()).hexdigest()
        msg       = f"{method.upper()}\n{path}\n{query}\n{body_hash}\n{ts}"
        sig       = hmac.new(keys["secret"].encode(), msg.encode(), hashlib.sha512).hexdigest()
        return {"KEY": keys["key"], "SIGN": sig, "Timestamp": ts, "Content-Type": "application/json"}

    deposits    = []
    withdrawals = []

    conn = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=conn) as sess:
        # 充值记录
        path  = "/api/v4/wallet/deposits"
        query = f"currency=USDT&from={start_ts}&to={end_ts}&limit=100"
        async with sess.get(f"{base}{path}?{query}", headers=_sign("GET", path, query)) as r:
            data = await r.json()
        if isinstance(data, list):
            for d in data:
                deposits.append({
                    "time":    _ts_to_str(int(d.get("timestamp", 0))),
                    "amount":  d.get("amount", ""),
                    "coin":    d.get("currency", ""),
                    "network": d.get("chain", ""),
                    "status":  d.get("status", ""),
                    "txid":    d.get("txid", ""),
                    "address": d.get("address", ""),
                })
        elif isinstance(data, dict) and "label" in data:
            deposits.append({"error": str(data)})

        # 提现记录
        path  = "/api/v4/wallet/withdrawals"
        query = f"currency=USDT&from={start_ts}&to={end_ts}&limit=100"
        async with sess.get(f"{base}{path}?{query}", headers=_sign("GET", path, query)) as r:
            data = await r.json()
        if isinstance(data, list):
            for d in data:
                withdrawals.append({
                    "time":    _ts_to_str(int(d.get("timestamp", 0))),
                    "amount":  d.get("amount", ""),
                    "coin":    d.get("currency", ""),
                    "network": d.get("chain", ""),
                    "status":  d.get("status", ""),
                    "txid":    d.get("txid", ""),
                    "address": d.get("address", ""),
                    "fee":     d.get("fee", ""),
                })
        elif isinstance(data, dict) and "label" in data:
            withdrawals.append({"error": str(data)})

    return deposits, withdrawals


# ═══════════════════════════════════════════════════════════════
#  Bitget
# ═══════════════════════════════════════════════════════════════

async def _bitget(keys: dict, start_ms: int, end_ms: int):
    base = "https://api.bitget.com"

    def _sign(method: str, path: str) -> dict:
        ts  = str(int(time.time() * 1000))
        msg = ts + method.upper() + path
        sig = base64.b64encode(
            hmac.new(keys["secret"].encode(), msg.encode(), hashlib.sha256).digest()
        ).decode()
        return {
            "ACCESS-KEY":        keys["key"],
            "ACCESS-SIGN":       sig,
            "ACCESS-TIMESTAMP":  ts,
            "ACCESS-PASSPHRASE": keys["passphrase"],
            "Content-Type":      "application/json",
        }

    deposits    = []
    withdrawals = []

    conn = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=conn) as sess:
        # 充值记录
        path = f"/api/v2/spot/wallet/deposit-records?coin=USDT&startTime={start_ms}&endTime={end_ms}&limit=100"
        async with sess.get(f"{base}{path}", headers=_sign("GET", path)) as r:
            data = await r.json()
        for d in (data.get("data") or []):
            deposits.append({
                "time":    _ms_to_str(int(d.get("cTime", 0))),
                "amount":  d.get("amount", ""),
                "coin":    d.get("coin", ""),
                "network": d.get("chain", ""),
                "status":  d.get("status", ""),
                "txid":    d.get("tradeId", ""),
                "address": d.get("address", ""),
            })

        # 提现记录
        path = f"/api/v2/spot/wallet/withdrawal-records?coin=USDT&startTime={start_ms}&endTime={end_ms}&limit=100"
        async with sess.get(f"{base}{path}", headers=_sign("GET", path)) as r:
            data = await r.json()
        for d in (data.get("data") or []):
            withdrawals.append({
                "time":    _ms_to_str(int(d.get("cTime", 0))),
                "amount":  d.get("amount", ""),
                "coin":    d.get("coin", ""),
                "network": d.get("chain", ""),
                "status":  d.get("status", ""),
                "txid":    d.get("tradeId", ""),
                "address": d.get("toAddress", ""),
                "fee":     d.get("fee", ""),
            })

    return deposits, withdrawals


# ═══════════════════════════════════════════════════════════════
#  打印
# ═══════════════════════════════════════════════════════════════

def _print_records(label: str, records: list[dict]):
    C = "\033[36m"; W = "\033[0m"; R = "\033[31m"; G = "\033[32m"; Y = "\033[33m"
    print(f"\n  {C}{label}{W}")
    if not records:
        print("    （无记录）")
        return
    for r in records:
        if "error" in r:
            print(f"    {R}查询失败: {r['error']}{W}")
            continue
        status = str(r.get("status", ""))
        # 状态着色
        if status in ("1", "2", "success", "FINISH", "done", "SUCCESS", "6"):
            sc = G
        elif status in ("0", "pending", "PENDING", "PROCESSING"):
            sc = Y
        else:
            sc = W
        amt  = r.get("amount", "")
        net  = r.get("network", "")
        txid = r.get("txid", "")
        addr = r.get("address", "")
        fee  = r.get("fee", "")
        fee_s = f"  手续费={fee}" if fee else ""
        txid_s = f"\n      TxID: {txid}" if txid else ""
        addr_s = f"\n      地址: {addr}" if addr else ""
        print(
            f"    {r.get('time',''):<20}  {amt:>10} USDT  "
            f"网络={net:<8}  {sc}状态={status}{W}{fee_s}"
            f"{txid_s}{addr_s}"
        )


# ═══════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════

async def _main(exchanges: list[str], start_ms: int, end_ms: int):
    from clients.api_keys_live import get_live_keys

    C = "\033[36m"; W = "\033[0m"; B = "\033[1m"

    fetchers = {
        "binance": _binance,
        "okx":     _okx,
        "gate":    _gate,
        "bitget":  _bitget,
    }

    tasks = {}
    for ex in exchanges:
        keys = get_live_keys(ex)
        if not keys or not keys.get("key"):
            print(f"[{ex}] 未配置实盘 API Key，跳过")
            continue
        tasks[ex] = fetchers[ex](keys, start_ms, end_ms)

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    print(f"\n{C}{'═'*65}{W}")
    print(f"{C}{B}  链上充值 / 提现记录 (USDT){W}")
    print(f"{C}{'═'*65}{W}")

    for ex, result in zip(tasks.keys(), results):
        print(f"\n{C}{B}{'─'*50}{W}")
        print(f"{C}{B}  {ex.upper()}{W}")
        if isinstance(result, Exception):
            print(f"  \033[31m查询异常: {result}\033[0m")
            continue
        deposits, withdrawals = result
        _print_records("【充值记录（入金）】", deposits)
        _print_records("【提现记录（出金）】", withdrawals)

    print(f"\n{C}{'═'*65}{W}\n")


def main():
    ap = argparse.ArgumentParser(description="查询各所链上 USDT 充提记录")
    ap.add_argument("--days", type=int, default=30, help="查询最近 N 天（默认 30）")
    ap.add_argument("--ex",   nargs="+",
                    default=["binance", "okx", "gate", "bitget"],
                    help="交易所列表")
    args = ap.parse_args()

    end_ms   = _now_ms()
    start_ms = end_ms - args.days * 86_400_000

    s = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    e = datetime.fromtimestamp(end_ms   / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    print(f"查询范围: {s} ~ {e} UTC  交易所: {args.ex}\n")

    asyncio.run(_main(args.ex, start_ms, end_ms))


if __name__ == "__main__":
    main()
