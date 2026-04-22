# Spread Hunter - 跨所价差套利系统 / Cross-Exchange Spread Arbitrage System

[中文](#中文文档) | [English](#english-documentation)

---

<a name="中文文档"></a>
## 中文文档

### 📋 项目概述

Spread Hunter 是一个**跨交易所价差套利系统**，通过监控多家加密货币交易所的永续合约价格差异，自动检测并执行统计套利策略。系统采用**低频、低延迟**设计，专注于高置信度的均值回归机会。

**核心特点：**
- **统计套利策略**：基于滚动中位数基准线，捕捉大所异动→小所延迟的价差机会
- **全自动化**：行情监控、信号检测、风险评估、下单执行、持仓管理全流程自动化
- **多交易所支持**：同时监控 4 家交易所（Binance、OKX、Gate、Bitget）
- **实时风控**：日止损、最大敞口、持仓超时、紧急平仓等多重保护机制
- **Latest-Wins 架构**：同一交易对的新信号自动取消旧任务，确保执行最新行情

---

### 🏗️ 项目架构

```
spread_hunter_python/
├── main.py                    # 主入口：启动 Tracker + Trader
├── tracker/                   # 行情监控模块
│   ├── tracker.py            # 主控制器：协调各组件
│   ├── ws_feed.py            # WebSocket 行情接收（多所并发）
│   ├── baseline.py           # 滚动中位数基准线计算
│   ├── signal_detector.py    # 异常检测算法（opportunity 信号生成）
│   ├── symbol_selector.py    # 动态标的筛选（按成交额排序）
│   ├── spread_logger.py      # 价差数据记录（CSV）
│   └── models.py             # 数据模型（Tick、MarketEvent）
├── trader/                    # 交易执行模块
│   ├── trader.py             # 主交易控制器（开平仓逻辑）
│   ├── exchange_client.py    # 交易所 REST API 客户端
│   ├── risk.py               # 风险管理（日止损、余额监控）
│   ├── position_manager.py   # 持仓管理
│   ├── cost_model.py         # 成本评估模型（手续费、滑点）
│   ├── orderbook.py          # 订单簿缓存（滑点评估）
│   ├── market_info.py        # 合约规格与资金费率
│   ├── position.py           # 持仓数据模型
│   └── config.py             # 交易参数配置
├── clients/                   # 交易所配置
│   ├── config.py             # WS/REST URL、标的格式转换
│   └── api_keys.py           # API 密钥（本地文件，不提交）
├── test/                      # 测试套件
│   ├── run_all.py            # 全量测试入口
│   ├── test_balance.py       # 余额查询测试
│   ├── test_positions.py     # 持仓查询测试
│   ├── test_cancel.py        # 限价单挂撤测试
│   ├── test_orders.py        # 市价单开平仓测试
│   ├── test_transfer.py      # 期货→现货划转测试
│   └── _common.py            # 测试公共工具
└── logs/                      # 日志输出目录
    ├── tracker.log           # 行情监控日志
    ├── trader.log            # 交易执行日志
    ├── main.log              # 主程序日志
    ├── spread_snapshots.csv  # 价差快照数据
    ├── signals.csv           # 交易信号记录
    └── positions.csv         # 持仓记录

```

---

### ⚙️ 核心组件说明

#### 1. 行情监控（Tracker）

| 组件 | 功能说明 |
|------|----------|
| **SymbolSelector** | 每 8 小时动态筛选 TOP N 交易标的，按 24h 成交额排序，取 5 所交集 |
| **WSFeed** | 并发连接 5 所 WebSocket，实时接收 tick 数据（bid/ask/mid） |
| **BaselineTracker** | 维护滚动中位数基准线（Rolling Median），每对交易所独立计算 |
| **SignalDetector** | 检测异常价差：大所异动（leader_move_pct）→ 小所延迟 → 生成 MarketEvent |
| **SpreadLogger** | 记录价差快照（CSV），用于事后分析策略表现 |

**信号生成逻辑：**
1. 计算大所价格相对其历史基准的变动率 `leader_move = (big_mid - big_base) / big_base`
2. 当 `leader_move > LEADER_MOVE_PCT`（默认 0.5%）时，认为大所发生显著异动
3. 检查小所价格是否滞后（未跟上大所变动）
4. 计算异常百分比 `anomaly_pct = (big_mid - small_mid) / small_base * 100`
5. 当 `abs(anomaly_pct) > ANOMALY_MIN_PCT`（默认 0.3%）时，生成交易信号

#### 2. 交易执行（Trader）

| 组件 | 功能说明 |
|------|----------|
| **Trader** | 主控制器：注册回调、调度开平仓任务、风控监控 |
| **ExchangeClient** | 统一封装 4 所 API（Binance、OKX、Gate、Bitget），支持测试网/Demo |
| **RiskManager** | 日止损（daily_loss）、最大敞口（max_exposure）、余额监控 |
| **PositionManager** | 持仓状态管理（open/closing/closed）、防重复开仓 |
| **CostModel** | 成本评估：预估净利润 = 价差收益 - 手续费 - 滑点 |
| **OrderBookCache** | 缓存实时订单簿，用于滑点评估 |

---

### 💰 交易逻辑详解

#### 开仓逻辑（_on_opportunity → _place_entry）

**1. 信号过滤（同步检查，μs 级延迟）**
```python
if abs(sig.anomaly_pct) < MIN_ANOMALY_TO_OPEN_PCT:  # 默认 0.3%
    return  # 异常太小，忽略

if not self.pm.can_open(big, small, sym):
    return  # 已有同方向持仓，或正在开仓中

ok, reason = self.risk.check_can_open(big, small, sym, notional)
if not ok:
    return  # 风控拒绝（余额不足、日止损、超敞口等）
```

**2. 资金计算**
- 单腿资金 = `min(各所余额) × PAIR_CAPITAL_PCT / 2`（默认 1% / 2 = 0.5%）
- 最低要求：单腿资金 ≥ `MIN_ORDER_NOTIONAL_USDT`（默认 50 USDT）
- 名义价值 = 单腿资金 × 2（两腿合计）

**3. 成本模型评估（cost_evaluate）**
```python
cr = cost_evaluate(ev, big, small, self.mi,
                   leg_budget=leg_budget,
                   small_ob=ob_pair.small,  # 实时订单簿
                   big_ob=ob_pair.big)
# 评估内容：
# - 预估成交价（考虑滑点）
# - 手续费（taker fee）
# - 净利润 = 价差收益 - 手续费 - 滑点
# - ROI = 净利润 / 占用资金
if not cr.should_trade:
    return  # 成本过高，放弃交易
```

**4. 并发下单**
```python
# 根据 anomaly 方向确定买卖方向
if direction == "long":   # 小所价格低，买小卖大
    small_side = "buy"
    big_side = "sell"
else:  # "short"
    small_side = "sell"
    big_side = "buy"

# 并发执行两腿下单
small_task = self.clients[small].place_order(...)
big_task = self.clients[big].place_order(...)
small_res, big_res = await asyncio.gather(small_task, big_task)
```

**5. 成交后处理**
- 创建 `Position` 对象（包含两腿成交信息）
- 添加到 `PositionManager`
- 通知 `RiskManager` 更新敞口
- 解冻基准线（`unfreeze_pair`），避免异常价格污染

#### 平仓逻辑（_on_tick → _do_exit）

**1. 触发条件（持续检查，1秒周期）**

| 条件 | 说明 |
|------|------|
| **收敛（convergence）** | `abs(anomaly_pct) <= CONVERGENCE_PCT`（默认 0.2%），价差回归正常 |
| **止损（stop_loss）** | 对于 long 仓位，`anomaly < -STOP_LOSS_PCT`（默认 1%）；short 相反 |
| **超时（timeout）** | `hold_seconds >= MAX_HOLD_SECONDS`（默认 1800s = 30分钟） |

**2. 平仓执行**
- 反向下单：如果开仓时小所 buy，则平仓时小所 sell
- 并发执行两腿平仓
- 计算实际 PnL = 平仓收益 - 开仓成本 - 手续费

**3. 异常处理**
- 如果一腿成功、一腿失败，触发**紧急平仓**（`_emergency_close`），撤销已成交的腿以恢复 delta 中性
- 记录失败日志，人工介入处理

---

### 🛡️ 风控系统

| 风控项 | 配置参数 | 说明 |
|--------|----------|------|
| **日止损** | `DAILY_HALT_PCT = 0.95` | 余额低于日初 95% 时停机（默认 5% 日止损） |
| **最大敞口** | `MAX_EXPOSURE_PCT = 0.20` | 总持仓名义价值 ≤ 总余额 20% |
| **最小下单** | `MIN_ORDER_NOTIONAL_USDT = 50` | 单腿名义价值 ≥ 50 USDT |
| **持仓超时** | `MAX_HOLD_SECONDS = 1800` | 超过 30 分钟强制平仓 |
| **异常阈值** | `MIN_ANOMALY_TO_OPEN_PCT = 0.3` | 异常百分比 ≥ 0.3% 才开仓 |
| **收敛阈值** | `CONVERGENCE_PCT = 0.2` | 异常回落到 0.2% 内平仓 |
| **止损阈值** | `STOP_LOSS_PCT = 1.0` | 亏损达 1% 强制止损 |

---

### 🚀 快速开始

#### 1. 安装依赖
```bash
pip install -r requirements.txt  # aiohttp, numpy, pandas 等
```

#### 2. 配置 API 密钥
在 `clients/api_keys.py` 中添加交易所 API 密钥：
```python
BINANCE_TESTNET_API_KEY = "your_key"
BINANCE_TESTNET_SECRET_KEY = "your_secret"
OKX_DEMO_API_KEY = "your_key"
OKX_DEMO_SECRET_KEY = "your_secret"
OKX_DEMO_PASSPHRASE = "your_passphrase"
# ... Gate、Bitget 同理
```

#### 3. 运行测试（测试网/Demo 环境）
```bash
# 测试所有交易所 API
python -m test.run_all

# 单个测试
python -m test.test_balance
python -m test.test_orders
```

#### 4. 启动系统（测试网）
```bash
python main.py
```

#### 5. 启动系统（主网实盘 ⚠️ 慎用）
```bash
python main.py --live
# 输入 YES 确认后启动
```

---

### 📊 关键配置参数

在 `trader/config.py` 和 `tracker/config.py` 中调整：

```python
# 交易参数
MIN_ANOMALY_TO_OPEN_PCT = 0.3      # 开仓最小异常百分比
CONVERGENCE_PCT = 0.2              # 平仓收敛阈值
STOP_LOSS_PCT = 1.0                # 止损阈值
MAX_HOLD_SECONDS = 1800            # 最大持仓时间
PAIR_CAPITAL_PCT = 0.01            # 单对占用资金比例（1%）

# 风控参数
DAILY_HALT_PCT = 0.95              # 日止损比例（5%）
MAX_EXPOSURE_PCT = 0.20            # 最大敞口比例

# 行情参数
TOP_N_SYMBOLS = 50                 # 监控标的数量
BASELINE_WARMUP_S = 300            # 基准线热身时间（秒）
LEADER_MOVE_PCT = 0.5              # 大所异动检测阈值
```

---

<a name="english-documentation"></a>
## English Documentation

### 📋 Overview

**Spread Hunter** is a cross-exchange statistical arbitrage system that monitors perpetual contract prices across multiple crypto exchanges to automatically detect and execute mean-reversion strategies. The system uses a **low-frequency, low-latency** design focused on high-confidence trading opportunities.

**Key Features:**
- **Statistical Arbitrage**: Based on rolling median baselines, captures price discrepancies where major exchanges lead and smaller exchanges lag
- **Fully Automated**: End-to-end automation from market data ingestion to position management
- **Multi-Exchange**: Monitors 4 exchanges simultaneously (Binance, OKX as majors; Gate, Bitget as minors)
- **Risk Management**: Daily loss limits, max exposure controls, position timeouts, emergency liquidation
- **Latest-Wins Architecture**: New signals for the same pair automatically cancel pending tasks, ensuring execution on the freshest data

---

### 🏗️ Architecture

```
spread_hunter_python/
├── main.py                    # Entry point: launches Tracker + Trader
├── tracker/                   # Market data module
│   ├── tracker.py            # Main controller
│   ├── ws_feed.py            # WebSocket feed handler (5 exchanges)
│   ├── baseline.py           # Rolling median baseline calculator
│   ├── signal_detector.py    # Anomaly detection algorithm
│   ├── symbol_selector.py    # Dynamic symbol selection by volume
│   ├── spread_logger.py      # Spread data logger (CSV)
│   └── models.py             # Data models (Tick, MarketEvent)
├── trader/                    # Trading execution module
│   ├── trader.py             # Main trading controller
│   ├── exchange_client.py    # Exchange REST API client
│   ├── risk.py               # Risk management
│   ├── position_manager.py   # Position management
│   ├── cost_model.py         # Cost evaluation (fees, slippage)
│   ├── orderbook.py          # Order book cache
│   ├── market_info.py        # Contract specs & funding rates
│   ├── position.py           # Position data models
│   └── config.py             # Trading parameters
├── clients/                   # Exchange configurations
│   ├── config.py             # WS/REST URLs, symbol format conversion
│   └── api_keys.py           # API keys (local file, not committed)
├── test/                      # Test suite
│   ├── run_all.py            # Full test runner
│   ├── test_balance.py       # Balance query test
│   ├── test_positions.py     # Position query test
│   ├── test_cancel.py        # Limit order test
│   ├── test_orders.py        # Market order test
│   ├── test_transfer.py      # Futures→spot transfer test
│   └── _common.py            # Test utilities
└── logs/                      # Log output directory
```

---

### 💰 Trading Logic Details

#### Entry Logic (_on_opportunity → _place_entry)

**1. Signal Filtering (sync, μs latency)**
```python
if abs(sig.anomaly_pct) < MIN_ANOMALY_TO_OPEN_PCT:  # default 0.3%
    return  # Anomaly too small, ignore

if not self.pm.can_open(big, small, sym):
    return  # Already have position or entry in progress

ok, reason = self.risk.check_can_open(big, small, sym, notional)
if not ok:
    return  # Risk control rejected
```

**2. Capital Calculation**
- Leg budget = `min(balances) × PAIR_CAPITAL_PCT / 2` (default 0.5% per leg)
- Minimum: leg budget ≥ `MIN_ORDER_NOTIONAL_USDT` (default 50 USDT)

**3. Cost Model Evaluation (cost_evaluate)**
- Uses real-time order book to estimate slippage
- Calculates: net profit = spread gain - fees - slippage
- Only executes if `cr.should_trade` is True

**4. Concurrent Execution**
- Determines direction based on anomaly sign
- Executes both legs concurrently (buy on small, sell on big for long)

**5. Post-Execution**
- Creates Position object with fill details
- Unfreezes baseline to prevent stale data

#### Exit Logic (_on_tick → _do_exit)

**Exit Conditions (checked every 1 second):**

| Condition | Description |
|-----------|-------------|
| **Convergence** | `abs(anomaly_pct) <= CONVERGENCE_PCT` (default 0.2%), spread normalized |
| **Stop Loss** | For long: `anomaly < -STOP_LOSS_PCT` (default 1%); opposite for short |
| **Timeout** | `hold_seconds >= MAX_HOLD_SECONDS` (default 1800s = 30min) |

**Emergency Handling:**
- If one leg fills but the other fails, triggers `_emergency_close` to reverse the filled leg and restore delta neutrality

---

### 🛡️ Risk Management

| Control | Parameter | Description |
|---------|-----------|-------------|
| **Daily Loss** | `DAILY_HALT_PCT = 0.95` | Halt when balance < 95% of day start (5% daily loss limit) |
| **Max Exposure** | `MAX_EXPOSURE_PCT = 0.20` | Total position notional ≤ 20% of total balance |
| **Min Order** | `MIN_ORDER_NOTIONAL_USDT = 50` | Minimum 50 USDT notional per leg |
| **Position Timeout** | `MAX_HOLD_SECONDS = 1800` | Force close after 30 minutes |
| **Entry Threshold** | `MIN_ANOMALY_TO_OPEN_PCT = 0.3` | Only enter when anomaly ≥ 0.3% |
| **Convergence** | `CONVERGENCE_PCT = 0.2` | Exit when anomaly converges to 0.2% |
| **Stop Loss** | `STOP_LOSS_PCT = 1.0` | Stop loss at 1% loss |

---

### 🚀 Quick Start

#### 1. Install Dependencies
```bash
pip install -r requirements.txt  # aiohttp, numpy, pandas
```

#### 2. Configure API Keys
Add exchange API keys in `clients/api_keys.py`:
```python
BINANCE_TESTNET_API_KEY = "your_key"
BINANCE_TESTNET_SECRET_KEY = "your_secret"
OKX_DEMO_API_KEY = "your_key"
OKX_DEMO_SECRET_KEY = "your_secret"
OKX_DEMO_PASSPHRASE = "your_passphrase"
# ... Gate, Bitget similarly
```

#### 3. Run Tests (Testnet/Demo)
```bash
python -m test.run_all
```

#### 4. Start System (Testnet)
```bash
python main.py
```

#### 5. Start System (Live Trading ⚠️ Use with caution)
```bash
python main.py --live
# Type YES to confirm
```

---

### 📊 Key Parameters

Adjust in `trader/config.py` and `tracker/config.py`:

```python
# Trading
MIN_ANOMALY_TO_OPEN_PCT = 0.3      # Min anomaly to open position
CONVERGENCE_PCT = 0.2              # Exit convergence threshold
STOP_LOSS_PCT = 1.0                # Stop loss threshold
MAX_HOLD_SECONDS = 1800            # Max position hold time
PAIR_CAPITAL_PCT = 0.01            # Capital per pair (1%)

# Risk
DAILY_HALT_PCT = 0.95              # Daily loss halt threshold
MAX_EXPOSURE_PCT = 0.20            # Max exposure ratio

# Market Data
TOP_N_SYMBOLS = 50                 # Number of symbols to monitor
BASELINE_WARMUP_S = 300            # Baseline warm-up time
LEADER_MOVE_PCT = 0.5              # Leader move detection threshold
```

---

### 📄 License

MIT License - For educational and research purposes. Trading cryptocurrencies carries significant risk.

---

**⚠️ Risk Warning**: This system involves real-time trading of cryptocurrency derivatives. Ensure you fully understand the code and risks before using live funds. Always test thoroughly on testnet/demo environments first.
