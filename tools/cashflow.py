"""
真实现金流查询工具。

从各交易所 API 拉取实际现金流记录（非估算），包含：
  - 合约交易盈亏（realized PnL）
  - 交易手续费（commission/fee）
  - 资金费率（funding fee）
  - 账户转入/转出（再平衡、充提币）

输出：tools/out/cashflow_YYYYMMDD_HHMMSS.csv（按时间升序）

用法：
    python -m tools.cashflow                  # 最近 7 天
    python -m tools.cashflow --days 30        # 最近 30 天
    python -m tools.cashflow --from 2025-01-01 --to 2025-01-31
    python -m tools.cashflow --ex gate        # 只查某所
"""

import argparse
import asyncio
import csv
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiohttp

# ── 输出目录 ──────────────────────────────────────────────────────────────────
_OUT_DIR = Path(__file__).parent / "out"
_OUT_DIR.mkdir(exist_ok=True)

# ── 类型映射（统一 category 字段）────────────────────────────────────────────
# category: trade_pnl | fee | funding | transfer | other

_BINANCE_TYPE_MAP = {
    "REALIZED_PNL": "trade_pnl",
    "COMMISSION":   "fee",
    "FUNDING_FEE":  "funding",
    "TRANSFER":     "transfer",
    "INSURANCE_CLEAR": "other",
    "WELCOME_BONUS":   "other",
    "REFERRAL_KICKBACK": "other",
}

_GATE_TYPE_MAP = {
    "pnl":  "trade_pnl",
    "fee":  "fee",
    "refr": "funding",
    "dnw":  "transfer",
    "fund": "other",
}

_OKX_SUBTYPE_MAP = {
    # subType 分类参考 OKX 文档（简化归类）
    "1":   "transfer",   # 存入
    "2":   "transfer",   # 提出
    "160": "fee",        # 手续费
    "161": "fee",        # 手续费退还（作为 fee，金额为正）
    "170": "trade_pnl",  # 合约盈亏
    "171": "trade_pnl",
    "172": "trade_pnl",
    "173": "trade_pnl",
    "174": "trade_pnl",
    "175": "trade_pnl",
    "176": "funding",    # 资金费
    "177": "funding",
}


# ═════════════════════════════════════════════════════════════════════════════
#  各所查询函数
# ═════════════════════════════════════════════════════════════════════════════

async def _fetch_binance(keys: dict, start_ms: int, end_ms: int, proxy: str) -> list[dict]:
    import hashlib, hmac
    from urllib.parse import urlencode
    from clients import get_rest_url

    base = get_rest_url("binance", testnet=False)
    rows = []

    async def _signed(session, params):
        params["timestamp"] = int(time.time() * 1000)
        qs  = urlencode(params)
        sig = hmac.new(keys["secret"].encode(), qs.encode(), hashlib.sha256).hexdigest()
        params["signature"] = sig
        return params, {"X-MBX-APIKEY": keys["key"]}

    px = {"proxy": proxy} if proxy else {}
    conn = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=conn) as sess:
        # Binance 单次最多 1000 条，按时间分批
        cur = start_ms
        while cur < end_ms:
            p, h = await _signed(sess, {"startTime": cur, "endTime": min(cur + 7*86400*1000, end_ms), "limit": 1000})
            async with sess.get(f"{base}/fapi/v1/income", params=p, headers=h, **px) as r:
                data = await r.json()
            if not isinstance(data, list):
                break
            for item in data:
                cat = _BINANCE_TYPE_MAP.get(item.get("incomeType", ""), "other")
                rows.append({
                    "exchange":  "binance",
                    "time_utc":  _ms_to_utc(int(item.get("time", 0))),
                    "timestamp": int(item.get("time", 0)) // 1000,
                    "category":  cat,
                    "contract":  item.get("symbol", ""),
                    "amount":    float(item.get("income", 0)),
                    "asset":     item.get("asset", "USDT"),
                    "raw_type":  item.get("incomeType", ""),
                    "note":      item.get("info", ""),
                    "tx_id":     str(item.get("tranId", "")),
                })
            if len(data) < 1000:
                break
            cur = int(data[-1]["time"]) + 1
    return rows


async def _fetch_okx(keys: dict, start_ms: int, end_ms: int, proxy: str) -> list[dict]:
    import base64, hashlib, hmac, json
    from clients import get_rest_url

    base = get_rest_url("okx", testnet=False)
    rows = []

    def _sign(path: str) -> dict:
        ts  = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        sig = base64.b64encode(
            hmac.new(keys["secret"].encode(), (ts + "GET" + path).encode(), hashlib.sha256).digest()
        ).decode()
        return {
            "OK-ACCESS-KEY": keys["key"], "OK-ACCESS-SIGN": sig,
            "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": keys["passphrase"],
        }

    px = {"proxy": proxy} if proxy else {}
    conn = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=conn) as sess:
        after = ""  # 分页游标
        while True:
            qs   = f"instType=SWAP&ccy=USDT&limit=100&begin={start_ms}&end={end_ms}"
            if after:
                qs += f"&after={after}"
            path = f"/api/v5/account/bills?{qs}"
            async with sess.get(f"{base}{path}", headers=_sign(path), **px) as r:
                data = await r.json()
            if data.get("code") != "0":
                break
            items = data.get("data") or []
            for item in items:
                sub  = str(item.get("subType", ""))
                cat  = _OKX_SUBTYPE_MAP.get(sub, "other")
                rows.append({
                    "exchange":  "okx",
                    "time_utc":  _ms_to_utc(int(item.get("ts", 0))),
                    "timestamp": int(item.get("ts", 0)) // 1000,
                    "category":  cat,
                    "contract":  item.get("instId", ""),
                    "amount":    float(item.get("balChg", 0)),
                    "asset":     item.get("ccy", "USDT"),
                    "raw_type":  item.get("type", "") + "/" + sub,
                    "note":      item.get("notes", ""),
                    "tx_id":     str(item.get("billId", "")),
                })
            if len(items) < 100:
                break
            after = items[-1].get("billId", "")
    return rows


async def _fetch_gate(keys: dict, start_ts: int, end_ts: int, proxy: str) -> list[dict]:
    import hashlib, hmac
    from clients import get_rest_url

    base = get_rest_url("gate", testnet=False)
    rows = []

    def _sign(method, path, query=""):
        ts        = str(int(time.time()))
        body_hash = hashlib.sha512(b"").hexdigest()
        msg       = f"{method.upper()}\n{path}\n{query}\n{body_hash}\n{ts}"
        sig       = hmac.new(keys["secret"].encode(), msg.encode(), hashlib.sha512).hexdigest()
        return {"KEY": keys["key"], "SIGN": sig, "Timestamp": ts}

    px = {"proxy": proxy} if proxy else {}
    conn = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=conn) as sess:
        offset = 0
        limit  = 100
        while True:
            q    = f"limit={limit}&offset={offset}&from={start_ts}&to={end_ts}"
            path = "/api/v4/futures/usdt/account_book"
            url  = f"{base}{path}?{q}"
            async with sess.get(url, headers=_sign("GET", path, q), **px) as r:
                data = await r.json()
            if not isinstance(data, list):
                break
            for item in data:
                cat = _GATE_TYPE_MAP.get(item.get("type", ""), "other")
                rows.append({
                    "exchange":  "gate",
                    "time_utc":  _ts_to_utc(int(item.get("time", 0))),
                    "timestamp": int(item.get("time", 0)),
                    "category":  cat,
                    "contract":  item.get("contract", ""),
                    "amount":    float(item.get("change", 0)),
                    "asset":     "USDT",
                    "raw_type":  item.get("type", ""),
                    "note":      item.get("text", ""),
                    "tx_id":     str(item.get("id", "")),
                })
            if len(data) < limit:
                break
            offset += limit
    return rows


async def _fetch_bitget(keys: dict, start_ms: int, end_ms: int, proxy: str) -> list[dict]:
    import base64, hashlib, hmac
    from clients import get_rest_url

    base = get_rest_url("bitget", testnet=False)
    rows = []

    def _sign(path: str) -> dict:
        ts  = str(int(time.time() * 1000))
        sig = base64.b64encode(
            hmac.new(keys["secret"].encode(), (ts + "GET" + path).encode(), hashlib.sha256).digest()
        ).decode()
        return {
            "ACCESS-KEY": keys["key"], "ACCESS-SIGN": sig,
            "ACCESS-TIMESTAMP": ts, "ACCESS-PASSPHRASE": keys["passphrase"],
        }

    # Bitget businessType 简化归类
    def _bitget_cat(bt: str) -> str:
        bt = bt.upper()
        if "FEE" in bt or "COMMISSION" in bt:
            return "fee"
        if "SETTLE" in bt or "PROFIT" in bt or "LOSS" in bt or "PNL" in bt:
            return "trade_pnl"
        if "FUNDING" in bt or "CAPITAL" in bt:
            return "funding"
        if "TRANSFER" in bt or "DEPOSIT" in bt or "WITHDRAW" in bt:
            return "transfer"
        return "other"

    px = {"proxy": proxy} if proxy else {}
    conn = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=conn) as sess:
        end_id = ""
        while True:
            qs   = f"productType=USDT-FUTURES&limit=100&startTime={start_ms}&endTime={end_ms}"
            if end_id:
                qs += f"&idLessThan={end_id}"
            path = f"/api/v2/mix/account/bills?{qs}"
            async with sess.get(f"{base}{path}", headers=_sign(path), **px) as r:
                data = await r.json()
            if str(data.get("code", "")) != "00000":
                break
            items = (data.get("data") or {}).get("bills") or data.get("data") or []
            if not isinstance(items, list):
                break
            for item in items:
                bt  = item.get("businessType", "")
                cat = _bitget_cat(bt)
                rows.append({
                    "exchange":  "bitget",
                    "time_utc":  _ms_to_utc(int(item.get("cTime", 0))),
                    "timestamp": int(item.get("cTime", 0)) // 1000,
                    "category":  cat,
                    "contract":  item.get("symbol", ""),
                    "amount":    float(item.get("amount", 0)),
                    "asset":     item.get("marginCoin", "USDT"),
                    "raw_type":  bt,
                    "note":      item.get("remark", ""),
                    "tx_id":     str(item.get("billId", "")),
                })
            if len(items) < 100:
                break
            end_id = items[-1].get("billId", "")
    return rows


# ═════════════════════════════════════════════════════════════════════════════
#  工具函数
# ═════════════════════════════════════════════════════════════════════════════

def _ms_to_utc(ms: int) -> str:
    if ms <= 0:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def _ts_to_utc(ts: int) -> str:
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ═════════════════════════════════════════════════════════════════════════════
#  主流程
# ═════════════════════════════════════════════════════════════════════════════

async def _main(exchanges: list[str], start_ms: int, end_ms: int, proxy: str):
    from clients.api_keys_live import get_live_keys

    all_rows: list[dict] = []

    fetchers = {
        "binance": _fetch_binance,
        "okx":     _fetch_okx,
        "gate":    _fetch_gate,
        "bitget":  _fetch_bitget,
    }

    tasks = {}
    for ex in exchanges:
        keys = get_live_keys(ex)
        if not keys or not keys.get("key"):
            print(f"[{ex}] 未配置实盘 API Key，跳过")
            continue
        tasks[ex] = fetchers[ex](keys, start_ms, end_ms, proxy)

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for ex, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            print(f"[{ex}] 查询失败: {result}")
        else:
            print(f"[{ex}] 获取 {len(result)} 条记录")
            all_rows.extend(result)

    if not all_rows:
        print("无记录")
        return

    # 按时间升序排列
    all_rows.sort(key=lambda r: r["timestamp"])

    # 输出 CSV
    ts_str  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _OUT_DIR / f"cashflow_{ts_str}.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "time_utc", "exchange", "category", "contract",
            "amount", "asset", "raw_type", "note", "tx_id",
        ])
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: row[k] for k in writer.fieldnames})

    print(f"\n共 {len(all_rows)} 条记录 → {out_path}")

    # 分类汇总
    from collections import defaultdict
    by_cat: dict[str, float] = defaultdict(float)
    by_ex_cat: dict[tuple, float] = defaultdict(float)
    for r in all_rows:
        by_cat[r["category"]] += r["amount"]
        by_ex_cat[(r["exchange"], r["category"])] += r["amount"]

    print("\n── 分类汇总 ─────────────────────────────────")
    print(f"  {'类别':<14} {'金额(USDT)':>12}")
    for cat in ["trade_pnl", "fee", "funding", "transfer", "other"]:
        v = by_cat.get(cat, 0.0)
        if v != 0:
            print(f"  {cat:<14} {v:>12.4f}")
    print(f"  {'合计':<14} {sum(by_cat.values()):>12.4f}")

    print("\n── 各所明细 ─────────────────────────────────")
    for (ex, cat), v in sorted(by_ex_cat.items()):
        if v != 0:
            print(f"  {ex:<10} {cat:<14} {v:>10.4f}")


def main():
    ap = argparse.ArgumentParser(description="真实现金流查询（从各交易所 API 获取）")
    ap.add_argument("--days", type=int, default=7, help="查询最近 N 天（默认 7）")
    ap.add_argument("--from", dest="date_from", help="起始日期 YYYY-MM-DD（覆盖 --days）")
    ap.add_argument("--to",   dest="date_to",   help="结束日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--ex",   nargs="+", default=["binance", "okx", "gate", "bitget"],
                    help="查询的交易所（默认全部）")
    ap.add_argument("--proxy", default="", help="HTTP 代理")
    args = ap.parse_args()

    now_ms  = int(time.time() * 1000)
    end_ms  = now_ms

    if args.date_to:
        end_ms = int(datetime.strptime(args.date_to, "%Y-%m-%d")
                     .replace(tzinfo=timezone.utc, hour=23, minute=59, second=59)
                     .timestamp() * 1000)
    if args.date_from:
        start_ms = int(datetime.strptime(args.date_from, "%Y-%m-%d")
                       .replace(tzinfo=timezone.utc).timestamp() * 1000)
    else:
        start_ms = now_ms - args.days * 86400 * 1000

    start_utc = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    end_utc   = datetime.fromtimestamp(end_ms   / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"查询范围: {start_utc} ~ {end_utc} UTC")
    print(f"交易所: {args.ex}\n")

    asyncio.run(_main(args.ex, start_ms, end_ms, args.proxy))


if __name__ == "__main__":
    main()
