# Operations and validation

[简体中文](OPERATIONS.zh-CN.md) · [Project overview](../README.md) · [Architecture](ARCHITECTURE.md)

This runbook separates observation, demo interaction, and live capital operations. Read the command and its confirmation behavior before execution; filenames such as `test_*` do not imply that a command is free of financial side effects.

## Operating modes

| Mode | Credentials | Possible side effects | Entry point |
|---|---|---|---|
| Tracker only | None for public feeds | Writes local logs | `python -m tracker` |
| Demo/testnet | Demo keys | Testnet orders and transfers | `python main.py` |
| Live read-only suite | Live keys | Account/API reads; no intended order or transfer | `python -m test_live.run_all` |
| Live trading | Live keys | Orders, transfers, fees, PnL | `python main.py --live` |
| Manual rebalance | Live keys plus withdrawal setup | Transfers or withdrawals when `--execute` is used | `python -m rebalance.run` |

All exchange-facing checks depend on external APIs and are integration checks. Run them in an environment whose IP allowlist, clock, network route, and account permissions match the intended deployment.

## Setup checklist

1. Use Python 3.10 or newer in an isolated environment.
2. Install `aiohttp`, `websockets`, `requests`, and `urllib3`; `orjson` is optional.
3. Create credential files from the examples described in [CONFIG_GUIDE.md](../CONFIG_GUIDE.md).
4. Confirm credential files, `.env` files, withdrawal addresses, and logs are ignored by Git.
5. Use separate demo and live keys. Apply IP restrictions and minimum permissions.
6. Review the checked-in values in `tracker/config.py` and `trader/config.py`.
7. Record dependency versions and the Git commit for any reproducible experiment.

## Validation ladder

Move downward only after the preceding layer behaves as expected.

### 1. Static validation

```bash
python -m compileall -q clients tracker trader rebalance tools test_demo test_live main.py
```

This catches syntax and import-compilation errors without contacting exchanges. It does not validate credentials or API compatibility.

### 2. Public market-data path

```bash
python -m tracker
```

Expected observations include a non-empty common symbol set, venue connections, completion of baseline warm-up, increasing Tick counts, and periodic spread snapshots. Stop with `Ctrl+C` and confirm that logs close cleanly.

### 3. Demo/testnet checks

```bash
# Lower-risk integration pass: skip order submission
python -m test_demo.run_all --skip-orders

# Full demo suite; may create testnet orders (transfers are a separate command)
python -m test_demo.run_all

# Limit the suite to one venue
python -m test_demo.run_all --ex binance --skip-orders
```

Demo environments differ from production and may not implement every endpoint. Treat a demo limitation separately from an application defect.

### 4. Live read-only checks

```bash
python -m test_live.run_all
python -m test_live.run_all --ex okx
```

Without `--money` or `--transfer`, the suite runs its safe group: connectivity and signatures, account reads, order-book access, and contract/funding metadata. Live credentials are still loaded, so secret handling remains critical.

### 5. Live checks with financial effects

```bash
# Includes order/cancel and minimum market-order checks
python -m test_live.run_all --money

# Adds the transfer group in dry-run form defined by the suite
python -m test_live.run_all --transfer
```

Read terminal prompts closely. These checks may reserve margin, trade, or incur fees. Use venue filters and minimal balances when isolating an adapter.

### 6. Application live mode

```bash
python main.py --live
```

The program first runs the read-only preflight. Continuing requires an exact uppercase `YES`. After confirmation, live startup may sweep spot USDT to futures accounts, load legacy positions, start the tracker and trader, and enable the rebalance supervisor. Review current code and configuration before relying on this description.

## Command risk classification

| Classification | Examples | Operator expectation |
|---|---|---|
| Local only | `compileall`, config dump | No network or capital effect |
| Public/read-only | tracker, reachability, public order book | Network requests and local logs |
| Authenticated read | account, balance, funding checks | Live secrets loaded; no intended capital movement |
| Order capable | live `--money`, `main.py --live` | Orders, fills, fees, and market exposure |
| Transfer capable | sweep and rebalance execution tools | Account transfers or withdrawals |

When uncertain, inspect `RUN.txt` and the command source before execution. Do not infer safety from a default flag without checking the current implementation.

## Runtime artifacts

| File | Interpretation |
|---|---|
| `logs/main.log` | Trader lifecycle, risk decisions, execution failures |
| `logs/tracker.log` | Connections, universe refresh, warm-up, tracker errors |
| `logs/signals.csv` | Detector output, including signals later rejected by execution gates |
| `logs/spread_snapshots.csv` | Periodic spread/baseline observations |
| `logs/trades.csv` | Open/close records and recorded PnL |
| `logs/params.json` | Tracker parameters captured at startup |

Archive the configuration snapshot with experimental outputs. Do not publish raw logs until they have been checked for account identifiers or other sensitive metadata.

## Shutdown and recovery

Normal shutdown is `Ctrl+C`/`SIGTERM`. The main process stops the tracker, trader, and rebalance supervisor, waits briefly for tasks, closes resources, and prints a session summary.

After a crash, network partition, or close-leg error:

1. Inspect positions and open orders directly in every venue account.
2. Run the account inspection utility before taking corrective action:

   ```bash
   python -m tools.check_account
   ```

3. Preview possible one-sided exposure without executing a close:

   ```bash
   python -m tools.close_naked_positions --dry-run
   ```

4. If a manual close is required, verify the tool's current flags and venue state first. A local position record is not authoritative; the exchange is.
5. Preserve logs and `logs/params.json` for incident analysis.

Do not restart automated trading until actual exchange positions, local assumptions, and balances agree.

## Rebalancing

Read-only inspection and planning:

```bash
python -m rebalance.check_balances
python -m rebalance.check_fees
python -m rebalance.run
```

Execution is deliberately separate:

```bash
python -m rebalance.run --execute
```

Execution may request withdrawals and requires configured destination addresses. Confirm asset, network, destination, fee, minimum withdrawal, and exchange maintenance state for every transfer. A successful API response is not the same as a confirmed destination credit.

## Reproducible research record

For each run intended for analysis, retain:

- Git commit and dirty-worktree status;
- Python and dependency versions;
- `logs/params.json` and relevant config diff;
- UTC start/end time and deployment region;
- exchange environment (demo or live) and enabled venue set;
- raw signal/spread logs plus a description of any data exclusions;
- failures, reconnects, manual interventions, and incomplete legs.

Separate detector metrics from execution metrics. Signal frequency, acceptance rate, fill rate, realized PnL, and operational failures answer different questions and should not be collapsed into one result.

## Known operational limits

- External API behavior and symbol schemas can change independently of this repository.
- No distributed lock prevents two live instances from acting on the same account.
- File logs are not a transactional source of truth.
- Cross-venue legs cannot be committed atomically.
- Demo results do not establish live fill quality.
- The repository has no bundled historical replay, deterministic unit-test suite, or continuous-integration workflow.
