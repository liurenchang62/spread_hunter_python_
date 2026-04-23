"""
实盘测试公共工具。

所有 test_live 测试文件从这里导入。
⚠️  本目录下所有测试使用实盘 API Key，涉及真实资金。
"""

import sys
import asyncio
import math
from pathlib import Path
from typing import Optional

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from trader.exchange_client import build_clients
from trader.market_info import MarketInfo, refresh_market_info
from trader.config import MIN_ORDER_NOTIONAL_USDT

# ─── 输出辅助 ────────────────────────────────────────────────────────────────
G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; C = "\033[36m"; W = "\033[0m"
B = "\033[1m"

def ok(msg):        print(f"  {G}[OK]  {msg}{W}")
def fail(msg):      print(f"  {R}[ERR] {msg}{W}")
def warn(msg):      print(f"  {Y}[!]   {msg}{W}")
def info(msg):      print(f"        {msg}")
def section(title): print(f"\n{C}{B}{'─'*56}\n  {title}\n{'─'*56}{W}")
def money(msg):     print(f"  {R}{B}[$$]  {msg}{W}")

# ─── 实盘测试合约（USDT-M 永续，各所最低流动性代币）──────────────────────────
# 使用 TRX（Tron）：价格低（约 $0.25），全 4 所均有合约，合约单位小
TEST_SYMBOL = {
    "binance": "TRXUSDT",
    "okx":     "TRX-USDT-SWAP",
    "gate":    "TRX_USDT",
    "bitget":  "TRXUSDT",
}

# 内部统一 symbol 名（用于 market_info 查询）
TEST_SYMBOL_INTERNAL = "TRXUSDT"

# ─── 客户端 ─────────────────────────────────────────────────────────────────

def load_live_clients() -> dict:
    """加载实盘客户端（live=True，使用 api_keys_live.py）。"""
    clients = build_clients(live=True, proxy="")
    if not clients:
        print(f"\n{R}[ERR] 无法加载实盘 API Key，请检查 clients/api_keys_live.py{W}\n")
    return clients

# ─── 市场信息 ────────────────────────────────────────────────────────────────

async def load_market_info(symbols: set[str] | None = None) -> MarketInfo:
    """拉取一次市场信息（合约规格）并返回。"""
    mi = MarketInfo()
    syms = symbols or {TEST_SYMBOL_INTERNAL}
    await refresh_market_info(mi, syms, proxy="", live=True)
    return mi

# ─── 最小下单量计算 ──────────────────────────────────────────────────────────

def compute_min_qty(mi: MarketInfo, exchange: str, symbol_internal: str,
                    ref_price: float) -> tuple[float, float]:
    """
    计算满足交易所最小要求且 >= MIN_ORDER_NOTIONAL_USDT 的下单量。
    返回 (qty_base, notional_usdt)。
    当市场信息不可用时，回退到 leg_budget / ref_price 估算。
    """
    # 尝试用 calc_target_qty（已考虑 min_qty、qty_step、向上取整）
    qty = mi.calc_target_qty(exchange, symbol_internal,
                             MIN_ORDER_NOTIONAL_USDT, ref_price)

    if qty <= 0:
        # 无规格数据：直接按最小名义价值估算
        info_obj = mi.get_symbol_info(exchange, symbol_internal)
        if info_obj and info_obj.min_qty > 0:
            qty = info_obj.min_qty  # 使用交易所要求的最小数量
        else:
            qty = math.ceil(MIN_ORDER_NOTIONAL_USDT / ref_price * 10) / 10

    notional = qty * ref_price
    return qty, notional

# ─── 价格查询（公开接口）────────────────────────────────────────────────────

async def get_price(coin: str = "TRX", proxy: str = "") -> float:
    """从 Binance 期货公开接口获取当前价格。"""
    import aiohttp
    symbol_map = {
        "TRX":  "TRXUSDT",
        "BTC":  "BTCUSDT",
        "ETH":  "ETHUSDT",
        "SOL":  "SOLUSDT",
        "DOGE": "DOGEUSDT",
    }
    fallback = {"TRX": 0.25, "BTC": 88000.0, "ETH": 1600.0, "SOL": 130.0, "DOGE": 0.12}
    sym = symbol_map.get(coin.upper(), f"{coin.upper()}USDT")
    url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={sym}"
    try:
        async with aiohttp.ClientSession() as sess:
            kw = {"proxy": proxy} if proxy else {}
            async with sess.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=5), **kw) as r:
                data = await r.json()
        return float(data.get("price", 0)) or fallback.get(coin.upper(), 1.0)
    except Exception:
        return fallback.get(coin.upper(), 1.0)

# ─── 用户确认 ────────────────────────────────────────────────────────────────

def confirm(prompt: str) -> bool:
    """要求用户明确输入 yes 才继续（涉及真实资金的操作必须调用）。"""
    resp = input(f"\n  {Y}{B}[真实资金操作]{W} {prompt}\n  输入 yes 继续，其他取消: ")
    return resp.strip().lower() == "yes"

def confirm_each(exchange: str, action: str) -> bool:
    resp = input(f"  {Y}确认在 {exchange.upper()} {action}？(yes/skip): {W}")
    return resp.strip().lower() == "yes"
