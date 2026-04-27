"""
导出当前机器的 trader/config.py 有效参数，便于与本机/服务器对比。

本机生成参考文件：
  cd /path/to/spread_hunter_python
  python -m tools.dump_trader_config --save trader_config.ref.txt

把 trader_config.ref.txt scp 到服务器后，在服务器项目根目录执行：
  python -m tools.dump_trader_config --compare trader_config.ref.txt

仅打印当前参数（人工对比）：
  python -m tools.dump_trader_config
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# 与交易/风控相关的关键项（顺序固定，输出稳定）
_KEYS: list[str] = [
    "LIVE_TRADING_ON",
    "TESTNET_EXCHANGES",
    "PAIR_CAPITAL_PCT",
    "PAIR_CAPITAL_FALLBACK_USDT",
    "MIN_ORDER_NOTIONAL_USDT",
    "MAX_POSITIONS_PER_PAIR",
    "MAX_POSITIONS_PER_SYMBOL",
    "SESSION_MAX_ENTRIES",
    "MIN_ANOMALY_TO_OPEN_PCT",
    "MIN_NET_ROI",
    "HOLD_ESTIMATE_S",
    "SLIPPAGE_MULTIPLIER",
    "CONVERGENCE_PCT",
    "STOP_LOSS_PCT",
    "MAX_HOLD_SECONDS",
    "MARKET_INFO_REFRESH_H",
    "LEVERAGE",
    "DAILY_HALT_PCT",
    "REBALANCE_CHECK_INTERVAL_H",
    "REBALANCE_FLOOR_PCT",
    "REBALANCE_MIN_TRANSFER_PCT",
    "REBALANCE_FEE_CEIL_PCT",
    "REBALANCE_CONFIRM_TIMEOUT_S",
    "CASH_RATIO_MIN",
    "CASH_RATIO_RESUME",
    "REBALANCE_WARN_PCT",
    "MAX_EXPOSURE_PCT",
    "MAX_CONSECUTIVE_FAILS",
    "FAILURE_COOLDOWN_S",
    "MAX_ORDERS_PER_MIN",
    "BALANCE_REFRESH_S",
]


def _fmt(val) -> str:
    if val is None:
        return "None"
    if isinstance(val, bool):
        return "True" if val else "False"
    if isinstance(val, set):
        return ",".join(sorted(val))
    if isinstance(val, frozenset):
        return ",".join(sorted(val))
    if isinstance(val, Path):
        return str(val.resolve())
    if isinstance(val, float):
        return repr(val)
    if isinstance(val, int):
        return str(val)
    return repr(val)


def _load_cfg():
    import trader.config as cfg

    return cfg


def dump_lines() -> list[str]:
    cfg = _load_cfg()
    lines: list[str] = []
    for k in _KEYS:
        if hasattr(cfg, k):
            lines.append(f"{k}={_fmt(getattr(cfg, k))}")
        else:
            lines.append(f"{k}=<未在 config.py 中定义>")
    return lines


def _parse_ref(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="导出或对比 trader/config 参数")
    ap.add_argument(
        "--save",
        metavar="FILE",
        help="写入参考文件（给服务器 --compare 用）",
    )
    ap.add_argument(
        "--compare",
        metavar="FILE",
        help="与参考文件逐项对比，不一致时退出码 1",
    )
    args = ap.parse_args()

    lines = dump_lines()
    text = "\n".join(lines) + "\n"

    if args.save:
        p = Path(args.save)
        p.write_text(text, encoding="utf-8")
        print(f"已写入 {p.resolve()}（共 {len(lines)} 项）")
        return 0

    if args.compare:
        ref_path = Path(args.compare)
        if not ref_path.is_file():
            print(f"找不到参考文件: {ref_path}", file=sys.stderr)
            return 2
        ref = _parse_ref(ref_path)
        cur = {ln.partition("=")[0]: ln.partition("=")[2] for ln in lines}
        extra = set(ref) - set(_KEYS)
        if extra:
            print(f"（参考文件含未知项，已忽略: {sorted(extra)}）\n")
        mismatches: list[tuple[str, str, str]] = []
        for k in _KEYS:
            if k not in ref:
                continue
            if cur.get(k) != ref[k]:
                mismatches.append((k, ref[k], cur.get(k, "")))
        print(text)
        print("── 对比结果 ──")
        if not mismatches:
            print("与参考文件一致（仅对比参考文件中出现的键）。")
            return 0
        for k, rv, cv in mismatches:
            print(f"  [不一致] {k}")
            print(f"    参考: {rv}")
            print(f"    当前: {cv}")
        print(f"\n共 {len(mismatches)} 项不一致。")
        return 1

    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
