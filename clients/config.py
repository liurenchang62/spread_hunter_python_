"""
交易所客户端配置：集中管理所有交易所的连接参数、分级和格式转换。

如需新增交易所：
  1. 在 WS_URLS / REST_BASE / TESTNET_WS_URLS / TESTNET_REST_BASE 中添加 URL
  2. 在 EXCHANGE_TIERS 中定义分级（"big" 或 "small"）
  3. 在 to_exchange_fmt / from_raw_symbol 中添加格式转换逻辑
"""

from typing import Optional

# ─── 交易所分级 ───────────────────────────────────────────────────────────────
EXCHANGE_TIERS = {
    "binance": "big",
    "okx":     "big",
    "gate":    "small",
    "bitget":  "small",
}

# ─── 参与交易的交易所列表（可自由配置）──────────────────────────────────────
# 只有在此列表中的交易所才会被初始化和用于交易
ACTIVE_EXCHANGES: list[str] = ["binance", "okx", "gate", "bitget"]

# 根据 ACTIVE_EXCHANGES 动态计算大所/小所列表
BIG_EXCHANGES:   list[str] = [ex for ex in ACTIVE_EXCHANGES if EXCHANGE_TIERS.get(ex) == "big"]
SMALL_EXCHANGES: list[str] = [ex for ex in ACTIVE_EXCHANGES if EXCHANGE_TIERS.get(ex) == "small"]
ALL_EXCHANGES:   list[str] = ACTIVE_EXCHANGES.copy()

# ─── 测试网不支持的交易对黑名单（这些币种在测试网/模拟盘不存在）──────────────────
TESTNET_SYMBOL_BLACKLIST: set[str] = {
    "PIEVERSEUSDT",  # 测试网不存在
    "RAVEUSDT",      # 测试网不存在
    "BASEDUSDT",     # 测试网不存在
    "RIVERUSDT",     # 测试网不存在
    "XAUUSDT",       # 测试网不存在
    "XAGUSDT",       # 测试网不存在
    "ZECUSDT",       # 测试网不存在
    "SPKUSDT",       # 测试网不存在
    "ORDIUSDT",      # 测试网可能存在但流动性差
}

# ─── WebSocket 地址（主网 / 永续合约）────────────────────────────────────────
WS_URLS: dict[str, str] = {
    "binance": "wss://fstream.binance.com/stream",      # USDT-M 永续 combined
    "okx":     "wss://ws.okx.com:8443/ws/v5/public",    # OKX 公共频道
    "gate":    "wss://fx-ws.gateio.ws/v4/ws/usdt",      # Gate USDT 永续
    "bitget":  "wss://ws.bitget.com/v2/ws/public",      # Bitget USDT-M
}

# ─── REST 地址（主网）─────────────────────────────────────────────────────────
REST_BASE: dict[str, str] = {
    "binance": "https://fapi.binance.com",
    "okx":     "https://www.okx.com",
    "gate":    "https://api.gateio.ws",
    "bitget":  "https://api.bitget.com",
}

# ─── 测试网 WebSocket 地址 ───────────────────────────────────────────────────
TESTNET_WS_URLS: dict[str, str] = {
    # Binance 期货测试网（非现货）：wss://stream.binancefuture.com
    # tracker 行情仍走主网 WS，此处仅备注，不用于行情订阅
    "binance": "wss://stream.binancefuture.com/ws",
    "okx":     "wss://ws.okx.com:8443/ws/v5/public",       # OKX Demo 同主网地址，靠 header 区分
    "gate":    "wss://fx-ws-testnet.gateio.ws/v4/ws/usdt",  # Gate 独立测试网
    "bitget":  "wss://ws.bitget.com/v2/ws/public",          # Bitget Demo 同主网地址，靠 header 区分
}

# ─── 测试网 REST 地址（下单用）──────────────────────────────────────────────
TESTNET_REST_BASE: dict[str, str] = {
    "binance": "https://testnet.binancefuture.com",          # Binance USDT-M 期货测试网
    "okx":     "https://www.okx.com",                       # OKX Demo 同主网，靠 x-simulated-trading:1 区分
    "gate":    "https://api-testnet.gateapi.io",              # Gate 独立测试网
    "bitget":  "https://api.bitget.com",                    # Bitget Demo 同主网，靠 paptrading:1 区分
}

# ─── 标的格式转换 ────────────────────────────────────────────────────────────

def to_exchange_fmt(symbol: str, exchange: str) -> str:
    """
    内部格式 BTCUSDT → 各交易所的合约代码格式。
    
    Args:
        symbol: 内部格式，如 "BTCUSDT"
        exchange: 交易所 ID
    
    Returns:
        交易所特定格式的合约代码
    """
    base = symbol[:-4]  # 去掉末尾 USDT
    
    if exchange == "binance":
        return symbol.lower()                       # btcusdt
    elif exchange == "okx":
        return f"{base}-USDT-SWAP"                  # BTC-USDT-SWAP
    elif exchange == "gate":
        return f"{base}_USDT"                       # BTC_USDT
    elif exchange == "bitget":
        return symbol                               # BTCUSDT
    return symbol


def from_raw_symbol(raw: str, exchange: str) -> Optional[str]:
    """
    各交易所原始代码 → 内部 BTCUSDT 格式。
    
    Args:
        raw: 交易所返回的原始 symbol
        exchange: 交易所 ID
    
    Returns:
        内部格式如 "BTCUSDT"，不认识则返回 None
    """
    r = raw.upper()
    
    if exchange == "binance":
        return r if r.endswith("USDT") else None
    elif exchange == "okx":
        if r.endswith("-USDT-SWAP"):
            return r.replace("-USDT-SWAP", "") + "USDT"
    elif exchange == "gate":
        if r.endswith("_USDT"):
            return r.replace("_USDT", "") + "USDT"
    elif exchange == "bitget":
        return r if r.endswith("USDT") else None
    return None
