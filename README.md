# Spread Hunter — Cross-Exchange Perpetual Futures Arbitrage

**[中文文档 README.zh-CN.md](README.zh-CN.md)**

---

## Overview

Spread Hunter is a fully automated **cross-exchange statistical arbitrage system** for perpetual futures. Major exchanges (Binance/OKX) lead in price discovery; minor exchanges (Gate/Bitget) lag behind. The system opens a position on the lagging exchange and hedges on the leading exchange, then closes both legs when the spread reverts.

**Key features**
- Fully automated — market data → signal → cost check → concurrent orders → position management
- WebSocket real-time feeds, in-memory signal filtering (μs-level latency)
- Funding-rate aware — exits before unfavorable settlements, holds through favorable ones
- Multi-layer risk control — daily loss halt / stop-loss day-ban / concentration limit / auto rebalancing

---

## Architecture

```
main.py                     Entry: redeem earn → transfer to futures → load legacy positions
│
├── tracker/                Market data
│   ├── ws_feed.py          Concurrent WebSocket feeds for 4 exchanges (bid/ask/mid)
│   ├── baseline.py         Rolling median baseline per exchange pair
│   ├── signal_detector.py  Signal: major-exchange move + minor-exchange lag → MarketEvent
│   └── symbol_selector.py  Refresh TOP 50 symbols by volume every 8h (4-exchange intersection)
│
├── trader/                 Trading engine
│   ├── trader.py           Controller: entry / exit / timeout / funding exit
│   ├── exchange_client.py  REST clients for 4 exchanges (orders / balances / transfers / earn)
│   ├── risk.py             Daily halt / stop-loss day-ban / failure cooldown
│   ├── feishu_push.py      Feishu (Lark) notifications — live mode only (optional)
│   ├── cost_model.py       Net profit = spread gain − fees − slippage
│   ├── market_info.py      Contract specs + funding rates (refreshed every 4h)
│   └── config.py           All trading parameters
│
└── rebalance/
    └── supervisor.py       Every 4h: if any exchange < 20% of total cash → auto on-chain transfer
```

---

## Trading Logic

### 1. Signal Detection

On each tick from a major exchange:
1. Calculate the major exchange's price move over the past 1 second
2. If move ≥ `LEADER_MOVE_PCT` (0.3%) → significant move detected
3. For each minor exchange, compute: `anomaly = current spread − rolling median baseline`
4. If `|anomaly| ≥ ANOMALY_MIN_PCT` (0.5%) and direction matches → emit `MarketEvent`

`anomaly` measures **deviation from the historical baseline**, not the absolute spread. Persistent structural spreads are absorbed into the baseline; only sudden departures trigger signals.

### 2. Entry Conditions (all must pass)

| Condition | Parameter | Value |
|-----------|-----------|-------|
| Anomaly size | `MIN_ANOMALY_TO_OPEN_PCT` | ≥ 0.5% from baseline |
| Cost-positive | `MIN_NET_ROI` | Net ROI after fees/slippage ≥ 0.1% |
| Position limit | `MAX_POSITIONS_PER_PAIR` | Max 1 open position per pair |
| Concentration | `MAX_SYMBOL_NOTIONAL_PCT` | Symbol notional ≤ 30% of total equity |
| Balance | — | Futures available balance ≥ leg budget on each exchange |

**Capital per trade:** `min(exchange balances) × 1% ÷ 2` per leg (1% total), minimum 6 USDT  
**Order type:** Both legs placed concurrently as IOC market orders — no resting orders

### 3. Exit Conditions (by priority)

PnL is computed from actual fill prices — not from the baseline anomaly. This means new positions and legacy positions loaded from the exchange on startup are monitored identically.

```
combined_pnl_pct = unrealized_pnl(current prices) / total notional × 100%
```

| Priority | Trigger |
|----------|---------|
| 1 — Funding exit | Net funding rate < 0 AND settlement ≤ 5 min away |
| 2 — Take profit | `combined_pnl_pct ≥ 0.20%` (covers close fees ~0.10%, net ~0.10%) |
| 3 — Stop loss | `combined_pnl_pct ≤ −8%` — last resort; **no new entries for the rest of the day** |
| 4 — Timeout | Hold time ≥ 8h (fallback, normally never reached) |

**Funding rate sign convention:**
- Long position net rate = `big_exchange_rate − small_exchange_rate`
- Short position net rate = `small_exchange_rate − big_exchange_rate`
- Positive = favorable (hold); Negative = unfavorable (exit before settlement)

### 4. Emergency Handling

If one leg fills and the other fails, `_emergency_close` immediately reverses the filled leg to restore delta-neutrality and prevent unhedged exposure.

---

## Risk Controls

| Control | Parameter | Description |
|---------|-----------|-------------|
| Daily loss halt | `DAILY_HALT_PCT = 0.95` | Balance < 95% of day-start → close all, halt |
| Post-stop-loss ban | — | After any stop-loss exit, no new entries until UTC midnight |
| Concentration limit | `MAX_SYMBOL_NOTIONAL_PCT = 0.30` | All positions in one symbol ≤ 30% of equity |
| Failure cooldown | `MAX_CONSECUTIVE_FAILS = 3` | 3 consecutive failures → 5-min cooldown |
| Rate limit | `MAX_ORDERS_PER_MIN = 10` | Max 10 orders per exchange per minute |
| Rebalancing | `REBALANCE_FLOOR_PCT = 0.20` | Any exchange < 20% of total cash → auto top-up |

---

## Parameter Reference

### trader/config.py

```python
# ── Master Switch ────────────────────────────────────────────────────────────
LIVE_TRADING_ON           = False   # True = live mainnet; False = demo/testnet

# ── Capital ──────────────────────────────────────────────────────────────────
PAIR_CAPITAL_PCT          = 0.01    # Both legs combined = min(balances) × 1%
MIN_ORDER_NOTIONAL_USDT   = 6.0     # Minimum leg notional (USDT)
LEVERAGE                  = 1       # Contract leverage (1 = no borrowing)

# ── Position Limits ──────────────────────────────────────────────────────────
MAX_POSITIONS_PER_PAIR    = 1       # Max simultaneous positions per (big-small-symbol) pair
MAX_POSITIONS_PER_SYMBOL  = 3       # Max positions per symbol across all pairs
MAX_SYMBOL_NOTIONAL_PCT   = 0.30    # Symbol notional cap = total equity × 30%
SESSION_MAX_ENTRIES       = 1       # Max entries per session (None = unlimited)

# ── Entry ────────────────────────────────────────────────────────────────────
MIN_ANOMALY_TO_OPEN_PCT   = 0.5     # Anomaly ≥ 0.5% from baseline (50 bps)
MIN_NET_ROI               = 0.001   # Net ROI after fees/slippage ≥ 0.1%

# ── Cost Model ───────────────────────────────────────────────────────────────
HOLD_ESTIMATE_S           = 60.0    # Estimated hold time (s), for funding cost
SLIPPAGE_MULTIPLIER       = 0.5     # Slippage = BBO spread × 0.5

# ── Exit ─────────────────────────────────────────────────────────────────────
TAKE_PROFIT_PCT           = 0.20    # combined_pnl_pct ≥ 0.20% → take profit
STOP_LOSS_PCT             = 8.0     # combined_pnl_pct ≤ −8% → stop loss
MAX_HOLD_SECONDS          = 28800   # Fallback timeout (8h)
FUNDING_EXIT_BEFORE_S     = 300     # Exit N seconds before unfavorable settlement

# ── Risk ─────────────────────────────────────────────────────────────────────
DAILY_HALT_PCT            = 0.95    # Halt when balance < 95% of day-start
MAX_CONSECUTIVE_FAILS     = 3       # Cooldown after N consecutive failures
FAILURE_COOLDOWN_S        = 300     # Cooldown duration (seconds)
MAX_ORDERS_PER_MIN        = 10      # Max orders per exchange per minute
BALANCE_REFRESH_S         = 60      # Balance refresh interval (seconds)

# ── Rebalancing ──────────────────────────────────────────────────────────────
REBALANCE_CHECK_INTERVAL_H = 4      # Check interval (hours)
REBALANCE_FLOOR_PCT        = 0.20   # Trigger if any exchange < 20% of total cash
```

### tracker/config.py

```python
# ── Symbol Selection ─────────────────────────────────────────────────────────
TOP_N_SYMBOLS             = 50           # Symbols to monitor (4-exchange intersection)
SYMBOL_REFRESH_H          = 8            # Refresh interval (hours)
MIN_VOLUME_USDT           = 10_000_000   # Min 24h volume filter

# ── Baseline ─────────────────────────────────────────────────────────────────
BASELINE_WARMUP_S         = 60      # Warm-up period (seconds); no signals fired
BASELINE_WINDOW           = 2000    # Rolling window size (ticks)

# ── Signal Detection ─────────────────────────────────────────────────────────
LEADER_WINDOW_MS          = 1000    # Look-back window for major exchange move (ms)
LEADER_MOVE_PCT           = 0.3     # Major exchange trigger: move ≥ 0.3% in 1s
ANOMALY_MIN_PCT           = 0.5     # Minor exchange anomaly threshold: ≥ 0.5%
COOLDOWN_MS               = 2000    # Per-symbol per-direction cooldown (ms)
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

For deploying on a new server, see [`server/server_deployment_instructions.txt`](server/server_deployment_instructions.txt).

---

## Feishu Notifications (Optional)

Notifications fire only in live mode (`python main.py --live`). Demo/testnet is silent.

Events: **start**, **open position**, **close position**, **close leg failure**.

Override defaults via environment variables: `FEISHU_WEBHOOK`, `FEISHU_BOT_AUTHORIZATION`.

---

## Notes

- `clients/api_keys*.py` and `clients/withdrawal_addresses.py` are in `.gitignore` — never committed
- `trader/config.py` is tracked in git — parameter changes are versioned alongside code
- Always validate on demo/testnet before using live funds; arbitrage strategies can still lose money in volatile markets
