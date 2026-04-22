"""
各交易所 USDT 充值地址 — 模板（可提交 Git）。

复制为 withdrawal_addresses.py 后填入你的充值地址。
"""

ADDRESSES: dict[str, dict[str, str]] = {
    "binance": {"SOL": "", "TRX": "", "ETH": "", "BSC": "", "POL": ""},
    "okx":     {"SOL": "", "TRX": "", "ETH": "", "BSC": "", "ARB": "", "AVAX": ""},
    "gate":    {"SOL": "", "TRX": "", "ETH": "", "BSC": "", "ARB": "", "AVAX": ""},
    "bitget":  {"SOL": "", "TRX": "", "ETH": "", "BSC": "", "ARB": ""},
    "htx":     {"SOL": "", "TRX": "", "ETH": "", "BSC": "", "ARB": ""},
}

NETWORK_NAMES: dict[str, dict[str, str]] = {
    "binance": {"SOL": "SOL", "BSC": "BSC", "TRX": "TRX", "ETH": "ETH"},
    "okx":     {"SOL": "Solana", "BSC": "BSC", "TRX": "TRC20", "ETH": "ERC20"},
    "gate":    {"SOL": "SOL", "BSC": "BSC", "TRX": "TRX", "ETH": "ETH"},
    "bitget":  {"SOL": "SOL", "BSC": "BEP20", "TRX": "TRC20", "ETH": "ERC20"},
}

PREFERRED_NETWORKS = ["SOL", "BSC", "TRX", "ETH"]


def get_deposit_address(exchange: str, network: str) -> str:
    return ADDRESSES.get(exchange, {}).get(network, "")


def get_api_network_name(exchange: str, network: str) -> str:
    return NETWORK_NAMES.get(exchange, {}).get(network, network)


def get_supported_networks(source: str, target: str) -> list[str]:
    src_nets = set(ADDRESSES.get(source, {}).keys())
    tgt_nets = set(ADDRESSES.get(target, {}).keys())
    common   = src_nets & tgt_nets
    return [n for n in PREFERRED_NETWORKS if n in common]
