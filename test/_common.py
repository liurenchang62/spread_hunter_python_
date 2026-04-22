"""
公共工具：颜色输出、客户端加载、测试辅助。
所有测试文件均从这里导入。
"""
import sys
import asyncio
from pathlib import Path

# 确保项目根目录在 sys.path 中
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Windows 终端强制 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from trader.exchange_client import build_clients
from trader.config import PROXY_URL, LIVE_TRADING_ON

# ─── 颜色 ───────────────────────────────────────────────────────────────────
G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; C = "\033[36m"; W = "\033[0m"

def ok(msg):       print(f"  {G}[OK]  {msg}{W}")
def fail(msg):     print(f"  {R}[ERR] {msg}{W}")
def warn(msg):     print(f"  {Y}[!]   {msg}{W}")
def info(msg):     print(f"        {msg}")
def section(title): print(f"\n{C}{'─'*52}\n  {title}\n{'─'*52}{W}")

# ─── 客户端 ─────────────────────────────────────────────────────────────────

def load_clients(live: bool = False) -> dict:
    """加载所有已配置的交易所客户端（默认测试网/Demo 模式）。"""
    return build_clients(live=live, proxy=PROXY_URL)

# ─── 测试所 / 测试合约 ─────────────────────────────────────────────────────
# 每所最小测试合约（BTC USDT-M 永续），用于下单/撤单测试
# 注意：Bitget 测试使用模拟币合约 SBTCSUSDT（模拟币模式），如需使用标准合约请创建 PAP Trading 类型 API Key
TEST_SYMBOL = {
    "binance": "BTCUSDT",         # qty 单位 base coin，最小 0.001
    "okx":     "BTC-USDT-SWAP",   # sz 单位张数，1 张 = 0.01 BTC
    "gate":    "BTC_USDT",        # sz 单位张数，1 张 = 0.001 BTC
    "bitget":  "SBTCSUSDT",       # Demo: 模拟币模式合约（非标准BTCUSDT）
}

# 各所最小开仓数量（base coin 单位），用于 place_order / place_limit_order
MIN_QTY = {
    "binance": 0.001,
    "okx":     0.01,    # 1 张 = 0.01 BTC
    "gate":    0.001,
    "bitget":  0.01,    # Demo 模拟币合约最小下单量较大（SBTCSUSDT 约 0.01）
}

# 获取 BTC 当前市价（公开接口，无需认证）
async def get_btc_price(proxy: str = "") -> float:
    """从 Binance 公开接口获取 BTC 当前价格。"""
    import aiohttp
    url = "https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT"
    try:
        async with aiohttp.ClientSession() as sess:
            kw = {"proxy": proxy} if proxy else {}
            async with sess.get(url, ssl=False, **kw) as r:
                data = await r.json()
        return float(data.get("price", 0))
    except Exception:
        return 95000.0   # 兜底估算
