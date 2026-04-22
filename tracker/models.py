"""
核心数据结构。
"""

import time
from dataclasses import dataclass, field


class Tick:
    """
    一次最优盘口快照（bid1 / ask1）。
    ts_ns 用 monotonic_ns 做延迟计算；wall_ms 用系统时间做日志时间戳。
    """
    __slots__ = ("exchange", "symbol", "bid", "ask", "mid", "spread_bps", "ts_ns", "wall_ms")

    def __init__(self, exchange: str, symbol: str, bid: float, ask: float):
        self.exchange  = exchange
        self.symbol    = symbol
        self.bid       = bid
        self.ask       = ask
        self.mid       = (bid + ask) * 0.5
        self.spread_bps = (ask - bid) / self.mid * 10000 if self.mid > 0 else 0.0
        self.ts_ns     = time.monotonic_ns()
        self.wall_ms   = time.time() * 1000   # UTC 毫秒时间戳，用于写日志


@dataclass
class MarketEvent:
    """
    Tracker 对外输出的市场事件，trader 消费这个队列做决策。

    event_type:
      "opportunity"      — tracker 发现价差异常，可能值得开仓
                           direction / big_move_pct / detail 有值
      "position_update"  — 对某个已登记持仓的定时推送，供 trader 判断平仓
                           direction / big_move_pct / detail 为空/0
    """
    event_type:    str    # "opportunity" | "position_update"
    symbol:        str
    big_exchange:  str
    small_exchange: str
    anomaly_pct:   float  # 当前价差 - 基准（%，per-coin）
    baseline_pct:  float  # 滚动基准（%，per-coin）
    big_bid:       float
    big_ask:       float
    big_mid:       float
    small_bid:     float
    small_ask:     float
    small_mid:     float
    ts_ns:         int
    wall_ms:       float
    # opportunity 专有字段（position_update 时为空/0）
    direction:     str   = ""
    big_move_pct:  float = 0.0   # 大所近期移动幅度（%）
    detail:        str   = ""


# 向后兼容别名，后续统一用 MarketEvent
Signal = MarketEvent


@dataclass
class SpreadSnap:
    """
    某一时刻，大所-小所某对的价差快照（写入 CSV 用）。
    """
    wall_ms:      float
    symbol:       str
    big_ex:       str
    small_ex:     str
    big_bid:      float
    big_ask:      float
    big_mid:      float
    small_bid:    float
    small_ask:    float
    small_mid:    float
    spread_pct:   float   # (big_mid - small_mid) / small_mid * 100，per-coin %
    baseline_pct: float   # 该对的滚动中位数基准（%）
    anomaly_pct:  float   # spread_pct - baseline_pct（%）
