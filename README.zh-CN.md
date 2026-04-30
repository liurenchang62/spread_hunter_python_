# Spread Hunter — 跨交易所价差套利系统

**[English README](README.md)**

---

## 项目概述

Spread Hunter 是一个**跨交易所永续合约统计套利系统**。核心思路：大所（Binance/OKX）价格领先，小所（Gate/Bitget）跟随滞后——在滞后窗口内同时在小所开仓、大所对冲，等价差回归后平仓获利。

**系统特点**
- 全自动：行情接入 → 信号检测 → 成本评估 → 双腿下单 → 持仓管理，无需人工干预
- 低延迟：WebSocket 实时行情，信号过滤为纯内存操作（μs 级）
- 资金费感知：费率不利时在结算前自动平仓；费率有利时继续持有
- 多重风控：日止损 / 止损后当日停开仓 / 单标的集中度限制 / 多所自动再平衡

---

## 系统架构

```
main.py                     主入口：启动时自动赎回理财→划转到合约→清理残仓
├── tracker/                行情监控模块
│   ├── ws_feed.py          4所 WebSocket 并发接收（bid/ask/mid）
│   ├── baseline.py         滚动中位数基准（每对交易所独立维护）
│   ├── signal_detector.py  信号检测：大所异动 + 小所滞后 → MarketEvent
│   └── symbol_selector.py  每 8h 按成交额动态筛选 TOP 50 标的
├── trader/
│   ├── trader.py           主控制器：开仓 / 平仓 / 超时 / 资金费退出
│   ├── exchange_client.py  4所 REST 客户端（下单 / 余额 / 划转 / 赎回理财）
│   ├── risk.py             风控：日止损 / 止损当日停开 / 余额刷新
│   ├── feishu_push.py      飞书推送（实盘可选，见下方「飞书通知」）
│   ├── cost_model.py       成本评估：价差收益 - 手续费 - 滑点 = 净利润
│   ├── market_info.py      合约规格 + 资金费率（每 4h 刷新）
│   └── config.py           ← 所有交易参数（见下方参数说明）
└── rebalance/
    └── supervisor.py       每 4h 检查各所余额，不足 20% 时自动链上转账补充
```

---

## 交易逻辑

### 1. 信号检测（Tracker）

```
每个 tick（大所）:
  1. 计算大所在过去 1 秒内的价格变动幅度
  2. 若变动 >= LEADER_MOVE_PCT (0.3%)，认为大所发生有效异动
  3. 对每个小所计算:
       anomaly = 当前价差 - 历史滚动中位数基准
  4. 若 |anomaly| >= ANOMALY_MIN_PCT (0.5%) 且方向一致 → 发出 MarketEvent
```

`anomaly` 是**相对历史基准的偏差**，不是绝对价差。同一对交易所的固定结构性价差会被基准吸收，只有突发偏离才触发信号。

### 2. 开仓条件（全部满足才下单）

| 条件 | 参数 | 说明 |
|------|------|------|
| 异常幅度 | `MIN_ANOMALY_TO_OPEN_PCT = 0.5%` | 价差偏离基准 ≥ 0.5% |
| 成本可行 | `MIN_NET_ROI = 0.1%` | 扣除手续费+滑点后净 ROI ≥ 0.1% |
| 仓位未满 | `MAX_POSITIONS_PER_PAIR = 1` | 同一套利对最多 1 笔 |
| 标的集中度 | `MAX_SYMBOL_NOTIONAL_PCT = 30%` | 单标的名义价值 ≤ 总权益 30% |
| 余额充足 | — | 各所期货可用余额 ≥ 单腿资金 |

**资金分配：** 单腿资金 = `min(各所余额) × 1% ÷ 2`（两腿合计 1%），最低 6 USDT

**下单方式：** 两腿并发 IOC 市价单（Immediate-Or-Cancel），无挂单残留

### 3. 平仓条件（按优先级）

| 优先级 | 原因 | 触发条件 |
|--------|------|----------|
| 1 | **资金费退出** | 净资金费率 < 0（不利）且距结算 ≤ 5 分钟 |
| 2 | **止盈（收敛）** | `\|anomaly\| ≤ CONVERGENCE_PCT = 0.15%`，价差回归正常 |
| 3 | **止损** | anomaly 反向超过 `STOP_LOSS_PCT = 5%`；触发后**当日不再开新仓** |
| 4 | **兜底超时** | 持仓超过 `MAX_HOLD_SECONDS = 8h`（正常不触发） |

**资金费逻辑：**
- Long 仓位净费率 = `big所费率 - small所费率`
- Short 仓位净费率 = `small所费率 - big所费率`
- 正值 = 有利（继续持有）；负值 = 不利（结算前平仓）

### 4. 紧急处理

一腿成交、另一腿失败时，自动反向平掉已成交的腿（`_emergency_close`），恢复 delta 中性，避免单边敞口。

---

## 风控体系

| 风控项 | 参数 | 说明 |
|--------|------|------|
| 日止损 | `DAILY_HALT_PCT = 0.95` | 当日余额跌破日初 95% → 全部平仓并停机 |
| 止损后停开 | — | 任一仓位止损后，当天不再开新仓（UTC 0 点重置） |
| 单标的集中度 | `MAX_SYMBOL_NOTIONAL_PCT = 0.30` | 同一合约全部仓位 ≤ 总权益 30% |
| 连续失败冷却 | `MAX_CONSECUTIVE_FAILS = 3` | 连续 3 次下单失败 → 冷却 5 分钟 |
| 频率限制 | `MAX_ORDERS_PER_MIN = 10` | 每所每分钟最多 10 笔 |
| 再平衡 | `REBALANCE_FLOOR_PCT = 0.20` | 任一所资金 < 总量 20% → 自动链上补充 |

---

## 完整参数说明

### trader/config.py（交易参数，已纳入版本管理）

```python
# ── 主开关 ──────────────────────────────────────────────────────────────────
LIVE_TRADING_ON = False        # True = 主网实盘；False = 测试网/Demo

# ── 资金结构 ─────────────────────────────────────────────────────────────────
PAIR_CAPITAL_PCT          = 0.01   # 每对两腿合计资金 = min(各所余额) × 1%
MIN_ORDER_NOTIONAL_USDT   = 6.0    # 单腿最小名义价值（USDT），交易所要求下限
LEVERAGE                  = 1      # 合约杠杆（1 = 不借钱，风险最低）

# ── 仓位限制 ─────────────────────────────────────────────────────────────────
MAX_POSITIONS_PER_PAIR    = 1      # 同一套利对（big-small-symbol）最多同时 N 笔
MAX_POSITIONS_PER_SYMBOL  = 3      # 同一合约跨所有套利对最多 N 笔
MAX_SYMBOL_NOTIONAL_PCT   = 0.30   # 单标的名义价值上限 = 总权益 × 30%
SESSION_MAX_ENTRIES       = 1      # 本次启动最多开仓 N 笔（None = 不限，测试用）

# ── 开仓条件 ─────────────────────────────────────────────────────────────────
MIN_ANOMALY_TO_OPEN_PCT   = 0.5    # 价差偏离基准 ≥ 0.5% 才开仓（= 50 bps）
MIN_NET_ROI               = 0.001  # 扣费后净 ROI ≥ 0.1% 才开仓

# ── 成本模型 ─────────────────────────────────────────────────────────────────
HOLD_ESTIMATE_S           = 60.0   # 预估持仓时长（秒），用于资金费估算
SLIPPAGE_MULTIPLIER       = 0.5    # 滑点系数（BBO 价差 × 0.5，保守估计）

# ── 平仓条件 ─────────────────────────────────────────────────────────────────
CONVERGENCE_PCT           = 0.15   # |anomaly| ≤ 0.15% → 止盈平仓
STOP_LOSS_PCT             = 5.0    # anomaly 反向超 5% → 止损，当日停开仓
MAX_HOLD_SECONDS          = 28800  # 兜底超时（8h），正常由上述条件平仓
FUNDING_EXIT_BEFORE_S     = 300    # 费率不利时，结算前 N 秒平仓（5 分钟）

# ── 风控参数 ─────────────────────────────────────────────────────────────────
DAILY_HALT_PCT            = 0.95   # 余额跌破日初 95% → 日止损停机
MAX_CONSECUTIVE_FAILS     = 3      # 连续下单失败 N 次后进入冷却
FAILURE_COOLDOWN_S        = 300    # 冷却时长（秒）
MAX_ORDERS_PER_MIN        = 10     # 每所每分钟最大下单次数
BALANCE_REFRESH_S         = 60     # 账户余额后台刷新周期（秒）

# ── 再平衡 ───────────────────────────────────────────────────────────────────
REBALANCE_CHECK_INTERVAL_H = 4     # 检查周期（小时）
REBALANCE_FLOOR_PCT        = 0.20  # 单所资金 < 总量 20% → 触发再平衡
```

### tracker/config.py（行情参数）

```python
# ── 标的筛选 ─────────────────────────────────────────────────────────────────
TOP_N_SYMBOLS             = 50          # 监控标的数量（4所交集取前 N）
SYMBOL_REFRESH_H          = 8           # 标的列表刷新周期（小时）
MIN_VOLUME_USDT           = 10_000_000  # 24h 最低成交额（过滤低流动性标的）

# ── 基准追踪 ─────────────────────────────────────────────────────────────────
BASELINE_WARMUP_S         = 60     # 热身时间（秒），热身期只采集不发信号
BASELINE_WINDOW           = 2000   # 滚动窗口大小（tick 数），用于计算中位数

# ── 信号检测 ─────────────────────────────────────────────────────────────────
LEADER_WINDOW_MS          = 1000   # 检测大所在过去 N ms 内的价格变动
LEADER_MOVE_PCT           = 0.3    # 大所触发阈值：1秒内变动 ≥ 0.3%
ANOMALY_MIN_PCT           = 0.5    # 异常价差阈值：偏离基准 ≥ 0.5% 才发信号
COOLDOWN_MS               = 2000   # 同标的同方向冷却时间（毫秒）
```

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API 密钥（本地文件，不提交 git）
# clients/api_keys.py        ← 测试网密钥
# clients/api_keys_live.py   ← 实盘密钥
# clients/withdrawal_addresses.py ← 各所充值地址（再平衡用）

# 3. 启动（测试网/Demo）
python main.py

# 4. 启动（主网实盘，需将 config.py 中 LIVE_TRADING_ON = True）
python main.py --live
```

### 飞书通知（可选）

与参考项目 **同一机器人**（代码内默认 Webhook / `Authorization` 与 `cross_platform_arbitrage_system_livetrading` 的 `feishu_push.rs` 一致）。**仅 `python main.py --live` 主网实盘会推送**；`python main.py` Demo/测试网 **不推送**。

推送正文带 `【机器人】` 与 **【价差策略】Spread Hunter** 标识。事件：**开始交易**、**开仓**、**平仓**、**平仓单腿失败告警**。

可通过环境变量覆盖默认值（例如换群或轮换密钥）：`FEISHU_WEBHOOK`、`FEISHU_BOT_AUTHORIZATION`。

---

## 注意事项

- `clients/api_keys*.py` 和 `clients/withdrawal_addresses.py` 已在 `.gitignore`，不会提交
- `trader/config.py` 已纳入版本管理，修改参数后会随代码同步
- 实盘前请在测试网充分验证，套利策略在极端行情下仍有亏损风险
