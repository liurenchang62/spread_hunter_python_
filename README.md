# Spread Hunter — Cross-Exchange Spread Arbitrage System

**[中文文档 README.zh-CN.md](README.zh-CN.md)**

---

## Overview

Spread Hunter is a **cross-exchange perpetual futures statistical arbitrage system**. The core idea: major exchanges (Binance/OKX) lead in price discovery, while minor exchanges (Gate/Bitget) lag behind — within that lag window, open a position on the minor exchange and hedge on the major exchange, then close both legs when the spread reverts.

**Key Features**
- Fully automated: market data → signal detection → cost evaluation → concurrent order execution → position management
- Low latency: WebSocket real-time feeds, signal filtering is pure in-memory (μs-level)
- Funding-rate aware: exits before funding settlement when rate is unfavorable; holds when favorable
- Multi-layer risk controls: daily loss halt / stop-loss day-ban / per-symbol concentration limit / automatic cross-exchange rebalancing

---

## Architecture

```
main.py                     Entry: on startup, redeem earn → transfer to futures → close stale positions
├── tracker/                Market data module
│   ├── ws_feed.py          4-exchange concurrent WebSocket (bid/ask/mid)
│   ├── baseline.py         Rolling median baseline per exchange pair
│   ├── signal_detector.py  Signal: big-exchange move + small-exchange lag → MarketEvent
│   └── symbol_selector.py  Every 8h, select TOP 50 symbols by volume (4-exchange intersection)
├── trader/
│   ├── trader.py           Main controller: entry / exit / timeout / funding exit
│   ├── exchange_client.py  REST clients for 4 exchanges (orders / balances / transfers / earn)
│   ├── risk.py             Risk: daily halt / stop-loss day-ban / balance refresh
│   ├── feishu_push.py      Feishu (Lark) notifications — live mode only (optional)
│   ├── cost_model.py       Cost evaluation: spread gain - fees - slippage = net profit
│   ├── market_info.py      Contract specs + funding rates (refreshed every 4h)
│   └── config.py           ← All trading parameters (see below)
└── rebalance/
    └── supervisor.py       Every 4h: if any exchange < 20% of total cash → auto on-chain transfer
```

---

## Trading Logic

### 1. Signal Detection (Tracker)

```
On each tick from a major exchange:
  1. Calculate price move of major exchange over the past 1 second
  2. If move >= LEADER_MOVE_PCT (0.3%), the major exchange had a significant move
  3. For each minor exchange, compute:
       anomaly = current spread - rolling median baseline
  4. If |anomaly| >= ANOMALY_MIN_PCT (0.5%) and direction matches → emit MarketEvent
```

`anomaly` is the **deviation from the historical baseline**, not the absolute spread. Persistent structural spreads are absorbed into the baseline; only sudden departures trigger signals.

### 2. Entry Conditions (all must be satisfied)

| Condition | Parameter | Description |
|-----------|-----------|-------------|
| Anomaly size | `MIN_ANOMALY_TO_OPEN_PCT = 0.5%` | Spread deviation from baseline ≥ 0.5% (50 bps) |
| Cost-positive | `MIN_NET_ROI = 0.1%` | Net ROI after fees and slippage ≥ 0.1% |
| Position limit | `MAX_POSITIONS_PER_PAIR = 1` | Max 1 open position per arbitrage pair |
| Concentration | `MAX_SYMBOL_NOTIONAL_PCT = 30%` | Symbol notional ≤ 30% of total equity |
| Balance | — | Futures available balance ≥ leg budget on each exchange |

**Capital allocation:** leg budget = `min(exchange balances) × 1% ÷ 2` (1% total across both legs), minimum 6 USDT

**Order type:** Both legs placed concurrently as IOC market orders (Immediate-Or-Cancel), no resting orders

### 3. Exit Conditions (by priority)

Once a position is open, exits are driven by **actual fill-price PnL**, not the baseline anomaly. This works for both new positions (fill prices recorded at order time) and legacy positions loaded from the exchange on startup.

```
combined_pnl_pct = unrealized_pnl(current_prices) / total_notional × 100%
```

| Priority | Reason | Trigger |
|----------|--------|---------|
| 1 | **Funding exit** | Net funding rate < 0 (unfavorable) AND settlement ≤ 5 minutes away |
| 2 | **Take profit** | `combined_pnl_pct ≥ TAKE_PROFIT_PCT = 0.20%` — covers close fees (~0.10%), net ≈ 0.10% |
| 3 | **Stop loss** | `combined_pnl_pct ≤ −STOP_LOSS_PCT = −8%` — wide last-resort; triggers **no new entries for the rest of the day** |
| 4 | **Fallback timeout** | Hold time exceeds `MAX_HOLD_SECONDS = 8h` (normally never reached) |

**Why PnL-based (not anomaly-based):**
- After entry, the fill prices are known and fixed — actual P&L is directly measurable
- No baseline dependency means old positions from a previous session are monitored identically to new ones
- Exit logic is unified: new and legacy positions share the same `_check_exit_reason`

**Funding rate logic:**
- Long position net rate = `big_exchange_rate - small_exchange_rate`
- Short position net rate = `small_exchange_rate - big_exchange_rate`
- Positive = favorable (keep holding); Negative = unfavorable (exit before settlement)

### 4. Emergency Handling

If one leg fills but the other fails, `_emergency_close` automatically reverses the filled leg to restore delta-neutrality and prevent unhedged exposure.

---

## Risk Controls

| Control | Parameter | Description |
|---------|-----------|-------------|
| Daily loss halt | `DAILY_HALT_PCT = 0.95` | Balance drops below 95% of day-start → close all, halt |
| Post-stop-loss ban | — | After any stop-loss exit, no new entries until UTC midnight |
| Concentration limit | `MAX_SYMBOL_NOTIONAL_PCT = 0.30` | All positions in one symbol ≤ 30% of total equity |
| Failure cooldown | `MAX_CONSECUTIVE_FAILS = 3` | 3 consecutive order failures → 5-minute cooldown |
| Rate limit | `MAX_ORDERS_PER_MIN = 10` | Max 10 orders per exchange per minute |
| Rebalancing | `REBALANCE_FLOOR_PCT = 0.20` | Any exchange below 20% of total cash → auto top-up via on-chain transfer |

---

## Full Parameter Reference

### trader/config.py (tracked in git)

```python
# ── Master Switch ────────────────────────────────────────────────────────────
LIVE_TRADING_ON = False        # True = live mainnet; False = testnet/demo

# ── Capital Structure ────────────────────────────────────────────────────────
PAIR_CAPITAL_PCT          = 0.01   # Total budget per pair = min(balances) × 1%
MIN_ORDER_NOTIONAL_USDT   = 6.0    # Minimum leg notional (USDT) per exchange requirement
LEVERAGE                  = 1      # Contract leverage (1 = no borrowing, safest)

# ── Position Limits ──────────────────────────────────────────────────────────
MAX_POSITIONS_PER_PAIR    = 1      # Max simultaneous positions per (big-small-symbol) pair
MAX_POSITIONS_PER_SYMBOL  = 3      # Max positions per symbol across all pairs
MAX_SYMBOL_NOTIONAL_PCT   = 0.30   # Max symbol notional = total equity × 30%
SESSION_MAX_ENTRIES       = 1      # Max entries per session (None = unlimited, test mode)

# ── Entry Conditions ─────────────────────────────────────────────────────────
MIN_ANOMALY_TO_OPEN_PCT   = 0.5    # Anomaly must exceed 0.5% (50 bps) from baseline
MIN_NET_ROI               = 0.001  # Minimum net ROI after fees/slippage (0.1%)

# ── Cost Model ───────────────────────────────────────────────────────────────
HOLD_ESTIMATE_S           = 60.0   # Estimated hold time (seconds), for funding rate cost
SLIPPAGE_MULTIPLIER       = 0.5    # Slippage = BBO spread × 0.5 (conservative estimate)

# ── Exit Conditions ──────────────────────────────────────────────────────────
TAKE_PROFIT_PCT           = 0.20   # combined_pnl_pct ≥ 0.20% → take profit (covers fees, net ~0.10%)
STOP_LOSS_PCT             = 8.0    # combined_pnl_pct ≤ −8% → stop loss (wide, last resort)
MAX_HOLD_SECONDS          = 28800  # Fallback timeout (8h), normally not triggered
FUNDING_EXIT_BEFORE_S     = 300    # Exit N seconds before settlement if funding is unfavorable

# ── Risk Parameters ──────────────────────────────────────────────────────────
DAILY_HALT_PCT            = 0.95   # Halt when balance < 95% of day-start balance
MAX_CONSECUTIVE_FAILS     = 3      # Cooldown after N consecutive order failures
FAILURE_COOLDOWN_S        = 300    # Cooldown duration (seconds)
MAX_ORDERS_PER_MIN        = 10     # Max orders per exchange per minute
BALANCE_REFRESH_S         = 60     # Background balance refresh interval (seconds)

# ── Rebalancing ──────────────────────────────────────────────────────────────
REBALANCE_CHECK_INTERVAL_H = 4     # Check interval (hours)
REBALANCE_FLOOR_PCT        = 0.20  # Trigger rebalance if any exchange < 20% of total cash
```

### tracker/config.py (market data parameters)

```python
# ── Symbol Selection ─────────────────────────────────────────────────────────
TOP_N_SYMBOLS             = 50          # Number of symbols to monitor (4-exchange intersection)
SYMBOL_REFRESH_H          = 8           # Symbol list refresh interval (hours)
MIN_VOLUME_USDT           = 10_000_000  # Min 24h volume to filter out illiquid symbols

# ── Baseline Tracking ────────────────────────────────────────────────────────
BASELINE_WARMUP_S         = 60     # Warm-up time (seconds); data collected, no signals fired
BASELINE_WINDOW           = 2000   # Rolling window size (ticks) for median calculation

# ── Signal Detection ─────────────────────────────────────────────────────────
LEADER_WINDOW_MS          = 1000   # Look-back window to detect major exchange move (ms)
LEADER_MOVE_PCT           = 0.3    # Major exchange trigger: move ≥ 0.3% in 1 second
ANOMALY_MIN_PCT           = 0.5    # Minor exchange anomaly threshold: ≥ 0.5% from baseline
COOLDOWN_MS               = 2000   # Per-symbol per-direction cooldown (ms)
```

---

## Quick Start

```bash
# 1. Install dependencies
pip install aiohttp websockets requests urllib3
pip install orjson          # optional, faster JSON parsing

# 2. Configure API keys (local files, never committed to git)
# clients/api_keys_demo.py        ← demo/testnet keys
# clients/api_keys_live.py        ← live trading keys
# clients/withdrawal_addresses.py ← deposit addresses for rebalancing

# 3. Run on demo/testnet (LIVE_TRADING_ON = False)
python main.py

# 4. Run live (set LIVE_TRADING_ON = True in trader/config.py first)
python main.py --live
```

---

## Feishu Notifications (Optional)

Notifications are sent only in live mode (`python main.py --live`). Demo/testnet mode is silent.

Events pushed: **start**, **open position**, **close position**, **close leg failure alert**.

Override the defaults via environment variables: `FEISHU_WEBHOOK`, `FEISHU_BOT_AUTHORIZATION`.

---

## Notes

- `clients/api_keys*.py` and `clients/withdrawal_addresses.py` are in `.gitignore` and will never be committed
- `trader/config.py` is tracked in git — parameter changes are versioned alongside code
- Always validate on testnet before using live funds; arbitrage strategies can still lose money in volatile markets
