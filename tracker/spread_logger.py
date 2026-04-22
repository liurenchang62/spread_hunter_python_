"""
日志输出：两个 CSV 文件 + 终端打印。

logs/spread_snapshots.csv  — 每秒快照所有大-小所对的价差（用于后续分析开平仓时机）
logs/signals.csv            — 每次检测到开仓机会时记录一行
"""

import csv
import logging
import time
from pathlib import Path
from typing import Optional

from .config import SIGNAL_LOG, SPREAD_LOG
from clients import BIG_EXCHANGES, SMALL_EXCHANGES
from .baseline import BaselineTracker
from .models import Tick, MarketEvent, SpreadSnap

logger = logging.getLogger("tracker.logger")


# ─── CSV 写入工具 ─────────────────────────────────────────────────────────────

_SPREAD_HEADER = [
    "wall_ms", "symbol",
    "big_ex", "small_ex",
    "big_bid", "big_ask", "big_mid",
    "small_bid", "small_ask", "small_mid",
    "spread_pct", "baseline_pct", "anomaly_pct",
]

_SIGNAL_HEADER = [
    "wall_ms", "symbol", "direction",
    "big_ex", "small_ex",
    "big_mid", "small_bid", "small_ask", "small_mid",
    "big_move_pct", "anomaly_pct", "baseline_pct",
    "detail",
]


def _open_csv(path: Path, header: list[str], overwrite: bool = False):
    """打开 CSV，写表头。overwrite=True 时每次重启清空重写。"""
    mode = "w" if overwrite else "a"
    # append 模式下若文件已有内容则不重复写表头
    need_header = overwrite or not (path.exists() and path.stat().st_size > 0)
    f = open(path, mode, newline="", encoding="utf-8", buffering=1)
    w = csv.DictWriter(f, fieldnames=header)
    if need_header:
        w.writeheader()
    return f, w


# ─── 主类 ─────────────────────────────────────────────────────────────────────

class SpreadLogger:
    """
    使用方式：
        logger = SpreadLogger()
        logger.maybe_snap(tick, latest, baseline)   # 每个 tick 调用
        logger.log_signal(sig)                       # 机会事件写入时调用
        logger.close()                               # 退出时调用
    """

    def __init__(self):
        self._sf, self._sw = _open_csv(SPREAD_LOG,  _SPREAD_HEADER, overwrite=True)   # 快照每次覆盖
        self._lf, self._lw = _open_csv(SIGNAL_LOG, _SIGNAL_HEADER, overwrite=True)   # 信号每次覆盖

        # 节流：每个 (big, small, symbol) 对每秒最多快照一次
        self._last_snap: dict[tuple, float] = {}

        self.snap_count   = 0
        self.signal_count = 0

    # ─── 价差快照（每秒一次） ─────────────────────────────────────────────────

    def maybe_snap(
        self,
        tick: Tick,
        latest: dict[str, dict[str, Tick]],
        baseline: BaselineTracker,
    ):
        """
        在 tick 触发时调用。对所有大-小所对按 1s 节流写一行快照。
        """
        sym = tick.symbol
        sym_latest = latest.get(sym, {})
        now = time.time()

        # 当 tick 来自大所时，更新所有 big-small 对的快照
        if tick.exchange in BIG_EXCHANGES:
            for small in SMALL_EXCHANGES:
                st = sym_latest.get(small)
                if not st:
                    continue
                self._write_snap(tick, st, baseline, now)

        # 当 tick 来自小所时，更新所有大所和该小所的快照
        elif tick.exchange in SMALL_EXCHANGES:
            for big in BIG_EXCHANGES:
                bt = sym_latest.get(big)
                if not bt:
                    continue
                self._write_snap(bt, tick, baseline, now)

    def _write_snap(
        self,
        big: Tick,
        small: Tick,
        baseline: BaselineTracker,
        now: float,
    ):
        key = (big.exchange, small.exchange, big.symbol)
        if now - self._last_snap.get(key, 0) < 1.0:
            return
        self._last_snap[key] = now

        base = baseline.get_pair_baseline(big.exchange, small.exchange, big.symbol)
        if small.mid <= 0:
            return
        spread = (big.mid - small.mid) / small.mid * 100  # 百分比制
        anomaly = spread - base

        row = {
            "wall_ms":      f"{big.wall_ms:.0f}",
            "symbol":       big.symbol,
            "big_ex":       big.exchange,
            "small_ex":     small.exchange,
            "big_bid":      f"{big.bid:.6f}",
            "big_ask":      f"{big.ask:.6f}",
            "big_mid":      f"{big.mid:.6f}",
            "small_bid":    f"{small.bid:.6f}",
            "small_ask":    f"{small.ask:.6f}",
            "small_mid":    f"{small.mid:.6f}",
            "spread_pct":   f"{spread:.4f}",
            "baseline_pct": f"{base:.4f}",
            "anomaly_pct":  f"{anomaly:.4f}",
        }
        self._sw.writerow(row)
        self.snap_count += 1

    # ─── 信号日志 ─────────────────────────────────────────────────────────────

    def log_signal(self, sig: MarketEvent):
        row = {
            "wall_ms":      f"{sig.wall_ms:.0f}",
            "symbol":       sig.symbol,
            "direction":    sig.direction,
            "big_ex":       sig.big_exchange,
            "small_ex":     sig.small_exchange,
            "big_mid":      f"{sig.big_mid:.6f}",
            "small_bid":    f"{sig.small_bid:.6f}",
            "small_ask":    f"{sig.small_ask:.6f}",
            "small_mid":    f"{sig.small_mid:.6f}",
            "big_move_pct": f"{sig.big_move_pct:.4f}",
            "anomaly_pct":  f"{sig.anomaly_pct:.4f}",
            "baseline_pct": f"{sig.baseline_pct:.4f}",
            "detail":       sig.detail,
        }
        self._lw.writerow(row)
        self.signal_count += 1

    # ─── 终端彩色打印 ─────────────────────────────────────────────────────────

    @staticmethod
    def print_signal(sig: MarketEvent):
        ts = time.strftime("%H:%M:%S", time.localtime(sig.wall_ms / 1000))
        d_mark = "[LONG]" if sig.direction == "long" else "[SHORT]"
        print(
            f"\033[93m[{ts}] SIGNAL\033[0m "
            f"\033[96m{sig.symbol}\033[0m "
            f"{d_mark} "
            f"\033[92m{sig.big_exchange}\033[0m→\033[91m{sig.small_exchange}\033[0m "
            f"大所移动{sig.big_move_pct:+.3f}% "
            f"异常={sig.anomaly_pct:.3f}%(基准{sig.baseline_pct:.3f}%) "
            f"小所{sig.small_exchange}: bid={sig.small_bid:.4f} ask={sig.small_ask:.4f}"
        )

    # ─── 清理 ─────────────────────────────────────────────────────────────────

    def close(self):
        try:
            self._sf.flush(); self._sf.close()
            self._lf.flush(); self._lf.close()
        except Exception:
            pass
