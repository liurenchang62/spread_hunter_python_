"""
tracker 模块：多交易所价差跟踪与信号识别。

入口：
    python -m tracker.tracker

对外暴露：
    Tracker        — 主控制器，含 signal_queue（AsyncIO Queue）
    MarketEvent    — 市场事件（trader 模块消费）
"""

from .tracker import Tracker
from .models import MarketEvent, Tick, SpreadSnap

__all__ = ["Tracker", "MarketEvent", "Tick", "SpreadSnap"]
