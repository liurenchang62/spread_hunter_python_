"""
信号检测：大所异动 → 小所尚未跟上 → 发出做多/做空机会。

逻辑：
  1. 每收到大所的 tick，检查该所在过去 LEADER_WINDOW_MS 毫秒内的价格变动
  2. 如果变动超过 LEADER_MOVE_BPS，说明大所发生了明显异动
  3. 对每个小所计算当前异常价差（当前价差 - 基准价差）
  4. 异常价差超过阈值 → 发出机会事件（表示小所还没跟上）
  5. 同标的同方向设置冷却时间，避免短时间内重复触发
"""

import time
from collections import defaultdict, deque
from typing import Optional

from .config import (
    LEADER_WINDOW_MS, LEADER_MOVE_PCT, ANOMALY_MIN_PCT,
    COOLDOWN_MS, MIN_SMALL_MID,
)
from clients import BIG_EXCHANGES, SMALL_EXCHANGES
from .baseline import BaselineTracker
from .models import Tick, MarketEvent


class SignalDetector:

    def __init__(self):
        # 每个大所每个标的保存最近 1s 内的 (ts_ns, mid) 序列，用于计算大所移动幅度
        # key: (exchange, symbol)
        self._big_window: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=500))

        # 冷却时间：key = (small_exchange, symbol, direction)，值 = 上次触发 ts_ns
        self._cooldowns: dict[tuple, int] = {}

        # 统计
        self.total_signals = 0
        self._diag = defaultdict(int)

    def check(
        self,
        tick: Tick,
        latest: dict[str, dict[str, Tick]],
        baseline: BaselineTracker,
    ) -> list[MarketEvent]:
        """
        每收到一个 tick 调用一次。
        只在热身完成后、且 tick 来自大所时才产生机会事件。
        返回 MarketEvent 列表（通常 0-3 个）。
        """
        if not baseline.warmed_up:
            return []
        if tick.exchange not in BIG_EXCHANGES:
            return []

        big = tick.exchange
        sym = tick.symbol
        now_ns = tick.ts_ns

        # ── Step 1：更新大所价格窗口，计算近期移动幅度 ──────────────────────
        key_w = (big, sym)
        w = self._big_window[key_w]
        w.append((now_ns, tick.mid))

        # 清除窗口之外的旧数据
        cutoff = now_ns - LEADER_WINDOW_MS * 1_000_000
        while w and w[0][0] < cutoff:
            w.popleft()

        if len(w) < 2:
            return []

        oldest_mid = w[0][1]
        if oldest_mid <= 0:
            return []

        move_pct = (tick.mid - oldest_mid) / oldest_mid * 100  # 百分比
        abs_move = abs(move_pct)

        if abs_move < LEADER_MOVE_PCT:
            self._diag["no_big_move"] += 1
            return []

        self._diag["big_move_detected"] += 1

        # 方向：大所涨了 → 小所做多；大所跌了 → 小所做空
        direction = "long" if move_pct > 0 else "short"

        # ── Step 2：对每个小所检查异常价差 ─────────────────────────────────
        signals = []
        sym_latest = latest.get(sym, {})

        for small in SMALL_EXCHANGES:
            st = sym_latest.get(small)
            if not st:
                self._diag["no_small_tick"] += 1
                continue

            # 小所 tick 不能太旧（超过 5s 认为连接有问题）
            age_ms = (now_ns - st.ts_ns) / 1_000_000
            if age_ms > 5000:
                self._diag["stale_small"] += 1
                continue

            # 小所价格过低时跳过（防除零/防异常）
            if st.mid <= MIN_SMALL_MID:
                continue

            # 检查基准是否建立
            if not baseline.has_pair_baseline(big, small, sym):
                self._diag["no_baseline"] += 1
                continue

            anomaly = baseline.get_pair_anomaly(big, small, sym, tick.mid, st.mid)
            if anomaly is None:
                continue

            base_pct = baseline.get_pair_baseline(big, small, sym)  # 已是百分比

            # 方向校验：大所涨 → anomaly 应为正（大所比小所更贵）
            #            大所跌 → anomaly 应为负（大所比小所更便宜）
            direction_match = (direction == "long" and anomaly > 0) or \
                              (direction == "short" and anomaly < 0)

            if not direction_match:
                self._diag["direction_mismatch"] += 1
                continue

            if abs(anomaly) < ANOMALY_MIN_PCT:
                self._diag["anomaly_too_small"] += 1
                continue

            # 冷却检查
            ck = (small, sym, direction)
            last_fire = self._cooldowns.get(ck, 0)
            if (now_ns - last_fire) < COOLDOWN_MS * 1_000_000:
                self._diag["cooldown"] += 1
                continue

            # ── 触发信号 ──────────────────────────────────────────────────
            self._cooldowns[ck] = now_ns
            self.total_signals += 1
            self._diag["signal_fired"] += 1

            sig = MarketEvent(
                event_type    = "opportunity",
                symbol        = sym,
                big_exchange  = big,
                small_exchange= small,
                anomaly_pct   = anomaly,
                baseline_pct  = base_pct,
                big_bid       = tick.bid,
                big_ask       = tick.ask,
                big_mid       = tick.mid,
                small_bid     = st.bid,
                small_ask     = st.ask,
                small_mid     = st.mid,
                ts_ns         = now_ns,
                wall_ms       = tick.wall_ms,
                direction     = direction,
                big_move_pct  = move_pct,
                detail        = (
                    f"{big}→{small} {sym} {direction} "
                    f"大所移动{move_pct:+.2f}% "
                    f"异常{anomaly:+.2f}%(基准{base_pct:.2f}%)"
                ),
            )
            signals.append(sig)

        return signals

    def diag_summary(self) -> dict:
        return dict(self._diag)
