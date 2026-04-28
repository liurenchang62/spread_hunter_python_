# Spread Hunter — Cross-Exchange Spread Arbitrage System

**[中文版 README.zh-CN.md](README.zh-CN.md)**

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
├── server/                    # VPS: SFTP sync, SSH login helpers, SERVER_COMMANDS
│   ├── sync_to_server.py
│   ├── login.ps1 / login.bat
│   ├── SERVER_COMMANDS.txt
│   └── deploy_server.sh       # Optional: run on Linux VPS after clone/pull
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
python -m test_demo.run_all
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

### Server sync, login, VPS deploy (`server/`)

Do not push secrets through GitHub. Use `server/` helpers:

| Item | Purpose |
|------|---------|
| `pip install -r server/requirements.txt` | Dependencies for **`sync_to_server.py`** (Paramiko SFTP). |
| `python server/sync_to_server.py --mode all` | Upload non‑ignored workspace changes vs `HEAD` **and delete** on VPS when Git shows deletes. |
| `python server/sync_to_server.py --mode ignored` | Upload **gitignored** files (secrets / local config). Skips `.venv`, caches, `logs/`, …; add `--full-ignored` to upload all ignored paths. |
| Env vars | `SERVER_PASSWORD` (required), optional `SERVER_HOST` or `SPREAD_HUNTER_SERVER`, `SERVER_USER`, `SERVER_REMOTE`, `SERVER_PORT`. |
| `server\login.bat` | SSH login; prefers **PuTTY `plink`** (password via env); otherwise falls back to **`ssh.exe`** (keys or typed password). |
| `server/deploy_server.sh` | Run **on Linux VPS** after `git clone` / `git pull`: `chmod +x server/deploy_server.sh && ./server/deploy_server.sh` |

Operational details and scp snippets: **`server/SERVER_COMMANDS.txt`**.

---

### 📄 License

MIT License - For educational and research purposes. Trading cryptocurrencies carries significant risk.

---

**⚠️ Risk Warning**: This system involves real-time trading of cryptocurrency derivatives. Ensure you fully understand the code and risks before using live funds. Always test thoroughly on testnet/demo environments first.
