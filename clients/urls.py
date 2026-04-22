"""
交易所 URL 配置（公开信息，无敏感数据）。

包含：
    - WebSocket 地址（行情订阅）
    - REST API 地址（下单、查询）
    - 主网 / 测试网地址分离

注意：此文件不含 API Key，可安全提交到 Git。
"""

# ─── WebSocket 地址（主网 / 永续合约行情）────────────────────────────────────────
WS_URLS: dict[str, str] = {
    "binance": "wss://fstream.binance.com/stream",      # USDT-M 永续 combined
    "okx":     "wss://ws.okx.com:8443/ws/v5/public",    # OKX 公共频道
    "gate":    "wss://fx-ws.gateio.ws/v4/ws/usdt",      # Gate USDT 永续
    "bitget":  "wss://ws.bitget.com/v2/ws/public",      # Bitget USDT-M
    "htx":     "wss://api.hbdm.com/linear-swap-ws",     # HTX 线性永续
}

# ─── REST API 地址（主网 / 实盘交易）───────────────────────────────────────────
REST_BASE: dict[str, str] = {
    "binance": "https://fapi.binance.com",
    "okx":     "https://www.okx.com",
    "gate":    "https://api.gateio.ws",
    "bitget":  "https://api.bitget.com",
    "htx":     "https://api.hbdm.com",
}

# ─── WebSocket 地址（测试网 / Demo 行情）──────────────────────────────────────
TESTNET_WS_URLS: dict[str, str] = {
    "binance": "wss://stream.binancefuture.com/ws",      # Binance 期货测试网
    "okx":     "wss://ws.okx.com:8443/ws/v5/public",     # OKX Demo 同主网，靠 header 区分
    "gate":    "wss://fx-ws-testnet.gateio.ws/v4/ws/usdt", # Gate 独立测试网
    "bitget":  "wss://ws.bitget.com/v2/ws/public",       # Bitget Demo 同主网，靠 header 区分
    # "htx":   "",  # HTX 无测试网
}

# ─── REST API 地址（测试网 / Demo 交易）────────────────────────────────────────
TESTNET_REST_BASE: dict[str, str] = {
    "binance": "https://testnet.binancefuture.com",      # Binance USDT-M 期货测试网
    "okx":     "https://www.okx.com",                    # OKX Demo 同主网，靠 x-simulated-trading:1
    "gate":    "https://api-testnet.gateapi.io",         # Gate 独立测试网
    "bitget":  "https://api.bitget.com",                 # Bitget Demo 同主网，靠 paptrading:1
    # "htx":   "",  # HTX 无测试网
}


def get_ws_url(exchange: str, testnet: bool = False) -> str:
    """获取交易所 WebSocket 地址。"""
    if testnet:
        return TESTNET_WS_URLS.get(exchange, WS_URLS.get(exchange, ""))
    return WS_URLS.get(exchange, "")


def get_rest_url(exchange: str, testnet: bool = False) -> str:
    """获取交易所 REST API 地址。"""
    if testnet:
        return TESTNET_REST_BASE.get(exchange, REST_BASE.get(exchange, ""))
    return REST_BASE.get(exchange, "")
