"""
模拟盘 / 测试网 API 密钥 — 模板文件（可提交 Git）。

用法：复制为 clients/api_keys_demo.py 后填入真实 Key：
    copy clients\\api_keys_demo.example.py clients\\api_keys_demo.py   # Windows
    cp clients/api_keys_demo.example.py clients/api_keys_demo.py       # Linux/macOS
"""

# ─── Binance 期货测试网 ────────────────────────────────────────────────────────
BINANCE_TESTNET_API_KEY    = ""
BINANCE_TESTNET_SECRET_KEY = ""

# ─── OKX Demo Trading ─────────────────────────────────────────────────────────
OKX_DEMO_API_KEY    = ""
OKX_DEMO_SECRET_KEY = ""
OKX_DEMO_PASSPHRASE = ""

# ─── Gate.io 测试网 ────────────────────────────────────────────────────────────
GATE_TESTNET_API_KEY    = ""
GATE_TESTNET_SECRET_KEY = ""

# ─── Bitget Demo Trading ───────────────────────────────────────────────────────
BITGET_DEMO_API_KEY    = ""
BITGET_DEMO_SECRET_KEY = ""
BITGET_DEMO_PASSPHRASE = ""


def get_demo_keys(exchange: str) -> dict:
    """返回指定交易所的模拟盘 API Key 字典。"""
    return {
        "binance": {"key": BINANCE_TESTNET_API_KEY, "secret": BINANCE_TESTNET_SECRET_KEY},
        "okx":     {"key": OKX_DEMO_API_KEY, "secret": OKX_DEMO_SECRET_KEY, "passphrase": OKX_DEMO_PASSPHRASE},
        "gate":    {"key": GATE_TESTNET_API_KEY, "secret": GATE_TESTNET_SECRET_KEY},
        "bitget":  {"key": BITGET_DEMO_API_KEY, "secret": BITGET_DEMO_SECRET_KEY, "passphrase": BITGET_DEMO_PASSPHRASE},
    }.get(exchange, {})


def check_demo_keys() -> dict[str, bool]:
    """检查各交易所模拟盘 Key 是否已配置（非空）。"""
    return {
        "binance": bool(BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_SECRET_KEY),
        "okx":     bool(OKX_DEMO_API_KEY and OKX_DEMO_SECRET_KEY and OKX_DEMO_PASSPHRASE),
        "gate":    bool(GATE_TESTNET_API_KEY and GATE_TESTNET_SECRET_KEY),
        "bitget":  bool(BITGET_DEMO_API_KEY and BITGET_DEMO_SECRET_KEY and BITGET_DEMO_PASSPHRASE),
    }
