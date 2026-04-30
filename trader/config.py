"""
Trader 配置。

LIVE_TRADING_ON = False  → 测试网/Demo 模拟下单
LIVE_TRADING_ON = True   → 主网实盘（谨慎！）
"""

from pathlib import Path

# ─── 主开关 ───────────────────────────────────────────────────────────────────
LIVE_TRADING_ON = False   # False = 测试网模拟；True = 主网实盘

# 测试网支持的交易所（HTX 无测试网，暂不参与交易）
TESTNET_EXCHANGES = {"binance", "okx", "gate", "bitget"}

# ─── 资金结构 ─────────────────────────────────────────────────────────────────
# 每个套利对（big-small-symbol）两腿合计资金 = 各所最小余额 × PAIR_CAPITAL_PCT
# 单腿 = min_balance × PAIR_CAPITAL_PCT / 2 = min_balance × 0.5%
# 余额数据不可用时（首次刷新前）回退到 PAIR_CAPITAL_FALLBACK_USDT
PAIR_CAPITAL_PCT          = 0.01    # 两腿合计：各所最小余额的 1%（单腿 0.5%）
PAIR_CAPITAL_FALLBACK_USDT = 10.0   # 兜底静态值（两腿合计10 USDT，单腿5 USDT）
MIN_ORDER_NOTIONAL_USDT   = 6.0     # 最小下单名义价值（Binance/Bitget要求>=5 USDT，留1 USDT余量防价格波动）

MAX_POSITIONS_PER_PAIR   = 1    # 同一套利对同时最多 N 笔（小资金测试：1）
MAX_POSITIONS_PER_SYMBOL = 3    # 同一合约跨所有套利对最多 N 笔（小资金测试：3）
MAX_SYMBOL_NOTIONAL_PCT  = 0.30 # 单标的合计名义价值 <= 总权益 × 此比例（防集中）

# 每次启动的会话开仓上限（用于前期测试）
# None = 不限制，由流动性/仓位限制等正常逻辑控制
# N    = 本次启动累计开仓达到 N 笔后停止新开仓；全部平仓后进入纯监控模式
SESSION_MAX_ENTRIES: int | None = 1

# ─── 开仓条件 ─────────────────────────────────────────────────────────────────
MIN_ANOMALY_TO_OPEN_PCT = 0.5  # 开仓最低异常阈值（%），建议 >= tracker 的 ANOMALY_MIN_PCT
MIN_NET_ROI             = 0.001  # 最低净 ROI（相对每腿资金），0.001 = 0.1%
# 注：成本模型决策仅使用 MIN_NET_ROI，净利润绝对值仅用于日志展示

# ─── 成本模型参数 ─────────────────────────────────────────────────────────────
HOLD_ESTIMATE_S     = 60.0   # 预估持仓时长（秒），用于资金费率估算
SLIPPAGE_MULTIPLIER = 0.5    # 滑点保守系数：BBO 价差 × 此系数（仅进场，出场假设收敛）

# ─── 平仓条件 ─────────────────────────────────────────────────────────────────
# 止盈：双腿合并 PnL（来自价格变动，相对名义价值）达到阈值即平仓。
# 计算方式：pnl_pct = unrealized_pnl / total_notional × 100
# 0.20% 的毛 PnL 扣除平仓手续费（约 0.10%）≈ 净利润 0.10%，与 MIN_NET_ROI 对齐。
TAKE_PROFIT_PCT  = 0.20    # 双腿合并 PnL >= 此值 → 止盈平仓（%，宽松快速退出）
STOP_LOSS_PCT    = 8.0     # 双腿合并 PnL <= -此值 → 止损平仓（%，宽松兜底）
MAX_HOLD_SECONDS = 28800   # 兜底强平时间（秒），正常退出由费率/收敛/止损控制（8h）
FUNDING_EXIT_BEFORE_S = 300  # 费率不利时，结算前多少秒平仓（5min）

# ─── 市场信息刷新 ─────────────────────────────────────────────────────────────
MARKET_INFO_REFRESH_H = 4  # 合约规格 / 费率 / 资金费 刷新周期（小时）

# ─── 杠杆 ─────────────────────────────────────────────────────────────────────
LEVERAGE = 1  # 合约杠杆倍数（1 = 不借钱，安全边际最高）

# ─── 风控参数 ──────────────────────────────────────────────────────────────────
# 日止损：当日净盈亏跌至日初余额的 X% 时，触发日止损停机（关闭所有仓位后退出）
DAILY_HALT_PCT        = 0.95   # 亏损超过日初余额的 5%（剩余 95%）时触发（小资金测试保守值）

# ─── 资金再平衡 ────────────────────────────────────────────────────────────────
# 所有阈值均为比例，无绝对数值，适配任意资金规模。
REBALANCE_CHECK_INTERVAL_H  = 4      # 定时检查周期（小时）
REBALANCE_FLOOR_PCT         = 0.20   # 单所现金 < 总现金 × 此比例时触发再平衡
REBALANCE_MIN_TRANSFER_PCT  = 0.02   # 单笔最小转账 = 总现金 × 此比例（防微小操作）
REBALANCE_FEE_CEIL_PCT      = 0.005  # 手续费上限 = 转账金额 × 此比例（超过则放弃该路径）
REBALANCE_CONFIRM_TIMEOUT_S = 1800   # 等待提现到账的超时秒数（超时后告警并继续）

# 单所余额下降超过 X% 时打印警告（不停机，提醒人工补充或调仓）
REBALANCE_WARN_PCT    = 0.30   # 某所余额相比日初下降超过 30% 发出警告

# 连续下单失败 N 次后冷却（进入 exposure 类型暂停，自动恢复）
MAX_CONSECUTIVE_FAILS = 3
FAILURE_COOLDOWN_S    = 300    # 冷却时长（秒）

# 单所每分钟最大下单次数（防止触发交易所频率限制）
MAX_ORDERS_PER_MIN    = 10

# 账户余额后台刷新周期（秒）
BALANCE_REFRESH_S     = 60

# ─── 日志 ─────────────────────────────────────────────────────────────────────
LOGS_DIR  = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
TRADE_LOG = LOGS_DIR / "trades.csv"
