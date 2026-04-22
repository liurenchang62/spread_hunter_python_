"""
Trader 配置 — 模板（可提交 Git）。

复制为 config.py 后再改资金参数、风控等：
    copy trader\\config.example.py trader\\config.py
"""

from pathlib import Path

# ─── 主开关 ───────────────────────────────────────────────────────────────────
LIVE_TRADING_ON = False   # False = 测试网模拟；True = 主网实盘

# 测试网支持的交易所（与 ACTIVE_EXCHANGES 一致）
TESTNET_EXCHANGES = {"binance", "okx", "gate", "bitget"}

# ─── 资金结构 ─────────────────────────────────────────────────────────────────
PAIR_CAPITAL_PCT          = 0.01
PAIR_CAPITAL_FALLBACK_USDT = 10.0
MIN_ORDER_NOTIONAL_USDT   = 6.0

MAX_POSITIONS_PER_PAIR   = 1
MAX_POSITIONS_PER_SYMBOL = 3

# ─── 开仓条件 ─────────────────────────────────────────────────────────────────
MIN_ANOMALY_TO_OPEN_PCT = 0.5
MIN_NET_ROI             = 0.001

# ─── 成本模型参数 ─────────────────────────────────────────────────────────────
HOLD_ESTIMATE_S     = 60.0
SLIPPAGE_MULTIPLIER = 0.5

# ─── 平仓条件 ─────────────────────────────────────────────────────────────────
CONVERGENCE_PCT  = 0.15
STOP_LOSS_PCT    = 0.8
MAX_HOLD_SECONDS = 300

# ─── 市场信息刷新 ─────────────────────────────────────────────────────────────
MARKET_INFO_REFRESH_H = 4

# ─── 风控参数 ──────────────────────────────────────────────────────────────────
DAILY_HALT_PCT        = 0.95
REBALANCE_WARN_PCT    = 0.30
MAX_EXPOSURE_PCT      = 0.50

MAX_CONSECUTIVE_FAILS = 3
FAILURE_COOLDOWN_S    = 300

MAX_ORDERS_PER_MIN    = 10

BALANCE_REFRESH_S     = 300

# ─── 日志 ─────────────────────────────────────────────────────────────────────
LOGS_DIR  = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
TRADE_LOG = LOGS_DIR / "trades.csv"
