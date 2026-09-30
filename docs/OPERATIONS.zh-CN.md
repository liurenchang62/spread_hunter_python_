# 运行、验证与安全手册

[English](OPERATIONS.md) · [项目概览](../README.zh-CN.md) · [系统架构](ARCHITECTURE.zh-CN.md)

本手册将行情观察、Demo 交互和真实资金操作分开说明。执行前应阅读命令行为和确认机制；文件名中包含 `test_*` 并不代表命令一定没有资金副作用。

## 运行模式

| 模式 | 密钥 | 可能的副作用 | 入口 |
|---|---|---|---|
| 仅 Tracker | 公开行情无需密钥 | 写入本地日志 | `python -m tracker` |
| Demo/测试网 | Demo 密钥 | 测试网订单与划转 | `python main.py` |
| 实盘只读套件 | 实盘密钥 | 账户/API 查询；按设计不下单、不转账 | `python -m test_live.run_all` |
| 实盘交易 | 实盘密钥 | 下单、划转、手续费与盈亏 | `python main.py --live` |
| 手工再平衡 | 实盘密钥及提现配置 | 使用 `--execute` 时会转账或提现 | `python -m rebalance.run` |

所有面向交易所的检查都是依赖外部 API 的集成检查。部署环境的 IP 白名单、系统时钟、网络路由和账户权限应与正式运行环境一致。

## 初始化检查清单

1. 在隔离环境中使用 Python 3.10 或更高版本。
2. 安装 `aiohttp`、`websockets`、`requests`、`urllib3`；`orjson` 可选。
3. 按 [CONFIG_GUIDE.md](../CONFIG_GUIDE.md) 中的示例创建密钥文件。
4. 确认密钥、`.env`、提现地址和日志均被 Git 忽略。
5. Demo 与实盘使用不同密钥，并设置 IP 白名单和最小权限。
6. 阅读 `tracker/config.py` 与 `trader/config.py` 中当前提交的参数。
7. 对需要复现的实验，记录依赖版本和 Git commit。

## 分层验证

只有上一层行为符合预期后，才进入下一层。

### 1. 静态验证

```bash
python -m compileall -q clients tracker trader rebalance tools test_demo test_live main.py
```

该命令不连接交易所，可发现语法和导入编译问题，但不能验证密钥或 API 兼容性。

### 2. 公开行情链路

```bash
python -m tracker
```

预期现象包括：共同标的池非空、交易所连接建立、基准预热完成、Tick 计数持续增加、周期写入价差快照。用 `Ctrl+C` 停止，并确认日志正常关闭。

### 3. Demo/测试网检查

```bash
# 较低风险：跳过提交订单
python -m test_demo.run_all --skip-orders

# 完整 Demo 套件；可能创建测试网订单（划转是独立命令）
python -m test_demo.run_all

# 只检查单一交易所
python -m test_demo.run_all --ex binance --skip-orders
```

Demo 环境与生产环境并不完全一致，部分端点可能缺失。应区分测试网限制与应用缺陷。

### 4. 实盘只读检查

```bash
python -m test_live.run_all
python -m test_live.run_all --ex okx
```

不提供 `--money` 或 `--transfer` 时，套件运行安全组：连通性与签名、账户读取、订单簿、合约和资金费元数据。此过程仍会加载实盘密钥，因此密钥管理要求不变。

### 5. 有资金副作用的实盘检查

```bash
# 包含下单/撤单和最小市价单检查
python -m test_live.run_all --money

# 加入套件定义的划转 dry-run 组
python -m test_live.run_all --transfer
```

仔细阅读终端提示。这些检查可能占用保证金、成交或产生手续费。排查单个适配器时，应限定交易所并使用最低必要余额。

### 6. 应用实盘模式

```bash
python main.py --live
```

程序首先运行只读预检，只有输入完全匹配的大写 `YES` 才会继续。确认后，实盘启动过程可能将现货 USDT 划入合约账户、加载遗留持仓、启动 Tracker 与 Trader，并启用再平衡监督器。实际使用前应再次核对当前代码与配置。

## 命令风险分级

| 级别 | 示例 | 操作者预期 |
|---|---|---|
| 仅本地 | `compileall`、参数导出 | 无网络与资金影响 |
| 公开/只读 | Tracker、连通性、公开订单簿 | 发起网络请求并写本地日志 |
| 鉴权读取 | 账户、余额、资金费检查 | 加载实盘密钥；按设计不移动资金 |
| 可下单 | 实盘 `--money`、`main.py --live` | 订单、成交、手续费与市场敞口 |
| 可转账 | sweep 与再平衡执行工具 | 账户划转或链上提现 |

不确定时，先阅读 `RUN.txt` 和对应命令源码。不要仅根据默认参数推断安全性。

## 运行产物

| 文件 | 含义 |
|---|---|
| `logs/main.log` | Trader 生命周期、风控决策与执行错误 |
| `logs/tracker.log` | 连接、标的刷新、预热与 Tracker 错误 |
| `logs/signals.csv` | 检测器输出，包括后来被执行门槛拒绝的信号 |
| `logs/spread_snapshots.csv` | 周期价差与基准观测 |
| `logs/trades.csv` | 开平仓记录和已记录盈亏 |
| `logs/params.json` | 启动时捕获的 Tracker 参数 |

分析实验时应将参数快照与输出共同归档。原始日志公开前，应先检查账户标识等敏感元数据。

## 退出与故障恢复

正常退出使用 `Ctrl+C`/`SIGTERM`。主进程会停止 Tracker、Trader 和再平衡监督器，短暂等待任务结束，关闭资源并打印会话摘要。

发生崩溃、网络分区或单腿平仓错误后：

1. 直接在每个交易所账户检查持仓和挂单。
2. 先运行账户检查工具：

   ```bash
   python -m tools.check_account
   ```

3. 在不执行平仓的情况下预览潜在单边敞口：

   ```bash
   python -m tools.close_naked_positions --dry-run
   ```

4. 如需人工平仓，先再次确认工具当前参数和交易所状态。本地持仓记录不是最终真值，交易所账户才是。
5. 保留日志与 `logs/params.json` 用于事故分析。

只有在交易所真实持仓、本地假设和余额重新一致后，才能恢复自动交易。

## 资金再平衡

只读检查和规划：

```bash
python -m rebalance.check_balances
python -m rebalance.check_fees
python -m rebalance.run
```

执行命令被明确分离：

```bash
python -m rebalance.run --execute
```

执行可能发起提现，并要求预先配置目标地址。每笔转账都应核对币种、网络、地址、手续费、最低提现额和交易所维护状态。API 返回成功不等于目标账户已经到账。

## 可复现实验记录

用于分析的每次运行建议保留：

- Git commit 与工作区是否存在未提交改动；
- Python 和依赖版本；
- `logs/params.json` 及相关配置差异；
- UTC 起止时间和部署区域；
- 交易所环境（Demo/实盘）和启用的交易所集合；
- 原始信号/价差日志及数据排除规则；
- 错误、重连、人工干预和未完整成交的腿。

检测指标与执行指标应分开统计。信号频率、接受率、成交率、已实现盈亏与运维故障回答的是不同问题，不应合并成单一结果。

## 已知运维边界

- 外部 API 行为和合约格式可能独立于本仓库发生变化。
- 系统没有分布式锁，无法阻止两个实盘实例操作同一账户。
- 文件日志不是事务式真值来源。
- 跨交易所双腿无法原子提交。
- Demo 结果不能证明实盘成交质量。
- 仓库没有内置历史回放、确定性单元测试套件或持续集成工作流。
