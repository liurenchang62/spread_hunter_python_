"""
基准追踪器：用滚动中位数记录"正常情况下大所-小所的价差是多少"。

原理：大所和小所之间始终存在一个稳定的结构性价差（基差/摩擦），
只有当实时价差**超出这个基准**时，才是真正的交易机会。
如果不扣除基准直接看总价差，会产生大量假信号。
"""

import math
import time
from collections import deque
from typing import Optional

from .config import BASELINE_WINDOW, BASELINE_UPDATE_MS, BASELINE_WARMUP_S
from clients import BIG_EXCHANGES, SMALL_EXCHANGES
from .models import Tick


class BaselineTracker:
    """
    追踪两类基准：
    1. pair_baseline[(big, small, symbol)] = 大所mid vs 小所mid 的正常价差中位数（bps）
    2. ba_baseline[(exchange, symbol)]     = 某小所某标的的正常 bid-ask spread 中位数（bps）

    pair_baseline 用于跨所异常价差；ba_baseline 为小所买一卖一宽度基准（当前未参与信号条件）。
    """

    def __init__(self):
        # ── pair spread 基准 ──────────────────────────────────────────────────
        # key: (big_exchange, small_exchange, symbol)
        self._pair_buf:  dict[tuple, deque] = {}
        self.pair_base:  dict[tuple, float] = {}   # 中位数
        self._pair_last: dict[tuple, int]   = {}   # 上次更新的 monotonic_ns

        # ── 小所 bid-ask spread 基准 ──────────────────────────────────────────
        # key: (exchange, symbol)
        self._ba_buf:   dict[tuple, deque] = {}
        self.ba_base:   dict[tuple, float] = {}   # 中位数
        self._ba_last:  dict[tuple, int]   = {}

        # 热身控制
        self._start_time = time.time()
        self.warmed_up   = False

    # ─── 更新接口 ─────────────────────────────────────────────────────────────

    def update(self, tick: Tick, latest: dict[str, dict[str, Tick]]):
        """
        每收到一个新 tick 调用一次。
        - 更新小所的 bid-ask 基准（tick 来自小所时）
        - 更新大所-小所价差基准（tick 来自任一方时）
        """
        self._check_warmup()

        # 更新 bid-ask 基准
        if tick.exchange in SMALL_EXCHANGES:
            self._update_ba(tick)

        # 更新大-小 pair 基准
        sym_latest = latest.get(tick.symbol, {})
        if tick.exchange in BIG_EXCHANGES:
            # 这笔是大所 tick：和所有已知小所配对
            for small in SMALL_EXCHANGES:
                st = sym_latest.get(small)
                if st:
                    self._update_pair(tick, st)
        elif tick.exchange in SMALL_EXCHANGES:
            # 这笔是小所 tick：和所有已知大所配对
            for big in BIG_EXCHANGES:
                bt = sym_latest.get(big)
                if bt:
                    self._update_pair(bt, tick)

    # ─── 查询接口 ─────────────────────────────────────────────────────────────

    def get_pair_anomaly(
        self,
        big_exchange: str,
        small_exchange: str,
        symbol: str,
        big_mid: float,
        small_mid: float,
    ) -> Optional[float]:
        """
        返回当前价差 - 基准 = 异常价差（bps）。
        正值：大所比小所贵得更多，小所应当上涨（做多小所机会）。
        负值：大所比小所便宜得更多，小所应当下跌（做空小所机会）。
        None：基准尚未建立。
        """
        key = (big_exchange, small_exchange, symbol)
        base = self.pair_base.get(key)
        if base is None:
            return None
        if small_mid <= 0:
            return None
        current = (big_mid - small_mid) / small_mid * 100   # %，与 pair_base 单位一致
        return current - base

    def get_pair_baseline(self, big: str, small: str, symbol: str) -> float:
        """返回基准值（bps），未建立时返回 0.0。"""
        return self.pair_base.get((big, small, symbol), 0.0)

    def has_pair_baseline(self, big: str, small: str, symbol: str) -> bool:
        return (big, small, symbol) in self.pair_base

    # ─── 交易后基准控制 ───────────────────────────────────────────────────────

    def unfreeze_pair(self, big: str, small: str, symbol: str) -> None:
        """
        交易完成后调用：将该 pair 的 _pair_last 重置为 0，
        使下一个 tick 立即更新基准（而不是等节流周期）。
        实际效果：恢复正常基准更新，避免异常价格在窗口内残留太久。
        """
        key = (big, small, symbol)
        self._pair_last[key] = 0

    # ─── 内部方法 ─────────────────────────────────────────────────────────────

    def _check_warmup(self):
        if not self.warmed_up and (time.time() - self._start_time) >= BASELINE_WARMUP_S:
            self.warmed_up = True

    def _update_pair(self, big_tick: Tick, small_tick: Tick):
        key = (big_tick.exchange, small_tick.exchange, big_tick.symbol)
        now = max(big_tick.ts_ns, small_tick.ts_ns)

        # 节流：避免同一对在短时间内重复计算
        if (now - self._pair_last.get(key, 0)) < BASELINE_UPDATE_MS * 1_000_000:
            return
        self._pair_last[key] = now

        if small_tick.mid <= 0:
            return
        spread = (big_tick.mid - small_tick.mid) / small_tick.mid * 100  # 百分比制

        buf = self._pair_buf.setdefault(key, deque(maxlen=BASELINE_WINDOW))
        buf.append(spread)

        if len(buf) >= 20:   # 至少20个样本才计算中位数
            s = sorted(buf)
            self.pair_base[key] = s[len(s) // 2]

    def _update_ba(self, tick: Tick):
        key = (tick.exchange, tick.symbol)
        now = tick.ts_ns

        if (now - self._ba_last.get(key, 0)) < BASELINE_UPDATE_MS * 1_000_000:
            return
        self._ba_last[key] = now

        buf = self._ba_buf.setdefault(key, deque(maxlen=BASELINE_WINDOW))
        buf.append(tick.spread_bps)

        if len(buf) >= 20:
            s = sorted(buf)
            self.ba_base[key] = s[len(s) // 2]

    # ─── 诊断 ─────────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        return {
            "pair_baselines": len(self.pair_base),
            "ba_baselines":   len(self.ba_base),
            "warmed_up":      self.warmed_up,
        }
