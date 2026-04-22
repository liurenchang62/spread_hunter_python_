"""
Clients 包：交易所配置与连接管理。

包含模块：
    urls              - WebSocket/REST URL 配置（公开）
    config            - 交易所分级、标的格式转换（公开）
    api_keys_live     - 实盘 API Key（敏感，生产环境使用）
    api_keys_demo     - 模拟盘 API Key（开发测试使用）
    api_keys          - 向后兼容，自动根据 LIVE_TRADING_ON 选择 live/demo

安全说明：
    - api_keys_live.py、api_keys_demo.py、withdrawal_addresses.py 已加入 .gitignore
    - 服务器上应设置 600 权限保护
    - 实盘 Key 建议通过环境变量或独立文件加载

使用方法：
    from clients import WS_URLS, REST_BASE, get_keys, to_exchange_fmt
    from clients.config import BIG_EXCHANGES, SMALL_EXCHANGES
"""

# ─── URL 配置（公开）───────────────────────────────────────────────────────────
from .urls import (
    WS_URLS,
    REST_BASE,
    TESTNET_WS_URLS,
    TESTNET_REST_BASE,
    get_ws_url,
    get_rest_url,
)

# ─── 交易所分级与格式转换（公开）──────────────────────────────────────────────
from .config import (
    EXCHANGE_TIERS,
    ACTIVE_EXCHANGES,
    BIG_EXCHANGES,
    SMALL_EXCHANGES,
    ALL_EXCHANGES,
    TESTNET_SYMBOL_BLACKLIST,
    to_exchange_fmt,
    from_raw_symbol,
)

# ─── API Key 配置（根据环境自动选择）──────────────────────────────────────────
# 尝试导入 api_keys（向后兼容），否则根据 LIVE_TRADING_ON 动态选择
import os

# 检查环境变量或 trader.config 中的 LIVE_TRADING_ON
def _is_live_mode() -> bool:
    """判断是否为实盘模式。"""
    # 优先从环境变量读取
    live_env = os.getenv("LIVE_TRADING_ON", "").lower()
    if live_env in ("1", "true", "yes", "on"):
        return True
    if live_env in ("0", "false", "no", "off"):
        return False
    
    # 尝试从 trader.config 读取
    try:
        import trader.config as trader_cfg
        return getattr(trader_cfg, "LIVE_TRADING_ON", False)
    except ImportError:
        return False


def get_keys(exchange: str, live: bool = None) -> dict:
    """
    获取指定交易所的 API Key（自动根据 live 参数或环境选择）。
    
    Args:
        exchange: 交易所 ID (binance, okx, gate, bitget)
        live: True=实盘, False=模拟盘, None=自动判断
    
    Returns:
        dict: 包含 key, secret, (passphrase) 的字典
    """
    if live is None:
        live = _is_live_mode()
    
    if live:
        from .api_keys_live import get_live_keys
        return get_live_keys(exchange)
    else:
        from .api_keys_demo import get_demo_keys
        return get_demo_keys(exchange)


def check_keys(live: bool = None) -> dict[str, bool]:
    """
    检查各交易所 API Key 是否已配置。
    
    Args:
        live: True=检查实盘, False=检查模拟盘, None=自动判断
    
    Returns:
        dict: {exchange: True/False}
    """
    if live is None:
        live = _is_live_mode()
    
    if live:
        from .api_keys_live import check_live_keys
        return check_live_keys()
    else:
        from .api_keys_demo import check_demo_keys
        return check_demo_keys()


# ─── 向后兼容：尝试导入旧的 api_keys.py（如果存在）────────────────────────────
try:
    from .api_keys import (
        BINANCE_TESTNET_API_KEY,
        BINANCE_TESTNET_SECRET_KEY,
        OKX_DEMO_API_KEY,
        OKX_DEMO_SECRET_KEY,
        OKX_DEMO_PASSPHRASE,
        GATE_TESTNET_API_KEY,
        GATE_TESTNET_SECRET_KEY,
        BITGET_DEMO_API_KEY,
        BITGET_DEMO_SECRET_KEY,
        BITGET_DEMO_PASSPHRASE,
        # 主网实盘（如果旧文件有）
        BINANCE_API_KEY,
        BINANCE_SECRET_KEY,
        OKX_API_KEY,
        OKX_SECRET_KEY,
        OKX_PASSPHRASE,
        GATE_API_KEY,
        GATE_SECRET_KEY,
        BITGET_API_KEY,
        BITGET_SECRET_KEY,
        BITGET_PASSPHRASE,
    )
except ImportError:
    # 旧文件不存在，使用新接口
    pass


__all__ = [
    # URL 配置
    "WS_URLS",
    "REST_BASE",
    "TESTNET_WS_URLS",
    "TESTNET_REST_BASE",
    "get_ws_url",
    "get_rest_url",
    # 分级与格式
    "EXCHANGE_TIERS",
    "ACTIVE_EXCHANGES",
    "BIG_EXCHANGES",
    "SMALL_EXCHANGES",
    "ALL_EXCHANGES",
    "TESTNET_SYMBOL_BLACKLIST",
    "to_exchange_fmt",
    "from_raw_symbol",
    # API Key 接口
    "get_keys",
    "check_keys",
]
