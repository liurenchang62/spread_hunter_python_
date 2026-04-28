# Spread Hunter（中文版）

英文全文请见 [README.md](README.md)。

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
├── server/                    # 服务器同步、SSH 一键登录、运维说明（见 SERVER_COMMANDS）
│   ├── sync_to_server.py
│   ├── login.ps1 / login.bat
│   ├── SERVER_COMMANDS.txt
│   └── deploy_server.sh       # 可选：在 Linux VPS 上首次部署依赖时执行
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
python -m test_demo.run_all

# 单个测试
python -m test_demo.test_balance
python -m test_demo.test_orders
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

### 服务器同步、登录与部署（`server/`）

不向 GitHub 推送密钥时，可使用 `server/` 下的脚本与说明：

| 项 | 说明 |
|------|------|
| `pip install -r server/requirements.txt` | **`sync_to_server.py`** 所需依赖（SFTP）。 |
| `python server/sync_to_server.py --mode all` | 同步相对 `HEAD` 有改动的**未被 ignore** 文件，并在远端按 Git **删除** 已删路径，与本地工作区对齐。 |
| `python server/sync_to_server.py --mode ignored` | 仅同步 **`.gitignore` 的文件**（典型为密钥、`trader/config.py`、`env/` 等）；默认排除 `.venv`、缓存、`logs/` 等；加 `--full-ignored` 可同步全部被 ignore 的路径。 |
| 环境变量 | `SERVER_PASSWORD`（必填）；可选 `SERVER_HOST` / `SPREAD_HUNTER_SERVER`、`SERVER_USER`、`SERVER_REMOTE`、`SERVER_PORT`。 |
| `server\login.bat` | 一键 SSH；优先调用 **PuTTY `plink`**（从环境变量带密码）；未安装则回退 **`ssh.exe`**（需密钥或手动输密码）。 |
| `server/deploy_server.sh` | 在 **Linux 服务器仓库根目录**首次/重装依赖：`chmod +x server/deploy_server.sh && ./server/deploy_server.sh`。 |

详尽命令：`server/SERVER_COMMANDS.txt`。已跟踪代码在服务器仍用 **`git pull`**。

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

