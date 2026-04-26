"""
仓位管理器。

职责：
  - 存储并追踪所有 open/closing 仓位
  - 检查开仓限制（per-pair / per-symbol）
  - 记录交易日志到 trades.csv
  - 向 tracker 同步 active_positions
"""

import csv
import logging
import time
from pathlib import Path
from typing import Optional

from trader.config import (
    MAX_POSITIONS_PER_PAIR,
    MAX_POSITIONS_PER_SYMBOL,
    TRADE_LOG,
)
from trader.position import Leg, Position

logger = logging.getLogger("trader.pm")


class PositionManager:
    def __init__(self, tracker_active_set: set):
        """
        tracker_active_set: tracker.active_positions 的引用，
        PositionManager 负责往里 add/discard。
        """
        self._active_set = tracker_active_set
        self._positions: dict[str, Position] = {}   # id → Position
        self._ensure_log_header()

    # ─── 查询 ────────────────────────────────────────────────────────────────

    def open_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.status in ("open", "closing")]

    def get_position(self, pos_id: str) -> Optional[Position]:
        return self._positions.get(pos_id)

    def can_open(self, big: str, small: str, symbol: str) -> bool:
        """检查是否允许再开一笔新仓位（per-pair 和 per-symbol 双重限制）。"""
        can_open, _ = self.can_open_with_reason(big, small, symbol)
        return can_open

    def can_open_with_reason(self, big: str, small: str, symbol: str) -> tuple[bool, str]:
        """检查是否允许开仓，并返回拒绝原因。"""
        pair_count   = 0
        symbol_count = 0
        for p in self.open_positions():
            if p.big_exchange == big and p.small_exchange == small and p.symbol == symbol:
                pair_count += 1
            if p.symbol == symbol:
                symbol_count += 1
        if pair_count >= MAX_POSITIONS_PER_PAIR:
            return False, f"同对仓位已满({pair_count}/{MAX_POSITIONS_PER_PAIR})"
        if symbol_count >= MAX_POSITIONS_PER_SYMBOL:
            return False, f"同合约仓位已满({symbol_count}/{MAX_POSITIONS_PER_SYMBOL})"
        return True, ""

    # ─── 开/平仓 ─────────────────────────────────────────────────────────────

    def add_position(self, pos: Position) -> None:
        """登记新开仓位，同时通知 tracker。"""
        self._positions[pos.id] = pos
        self._active_set.add((pos.big_exchange, pos.small_exchange, pos.symbol))
        logger.info(
            f"[pm] 开仓 {pos.id} | {pos.symbol} | {pos.big_exchange}/{pos.small_exchange}"
            f" | dir={pos.direction} | anomaly={pos.open_anomaly_pct:.3f}%"
        )

    def mark_closing(self, pos_id: str) -> None:
        pos = self._positions.get(pos_id)
        if pos:
            pos.status = "closing"

    def close_position(
        self,
        pos_id: str,
        close_anomaly_pct: float,
        reason: str,
        small_close_result,
        big_close_result,
    ) -> Optional[Position]:
        """
        记录平仓结果，计算 PnL，写日志，从 active_set 移除。
        返回已关闭的 Position。
        """
        pos = self._positions.get(pos_id)
        if not pos:
            return None

        pos.status            = "closed"
        pos.close_anomaly_pct = close_anomaly_pct
        pos.close_time        = time.time()
        pos.close_reason      = reason

        # 保存平仓腿成交详情
        if small_close_result and small_close_result.success:
            pos.small_close_order_id = small_close_result.order_id
            pos.small_close_price    = small_close_result.fill_price
            pos.small_close_fee      = small_close_result.fee_usdt
        if big_close_result and big_close_result.success:
            pos.big_close_order_id = big_close_result.order_id
            pos.big_close_price    = big_close_result.fill_price
            pos.big_close_fee      = big_close_result.fee_usdt

        # 计算 PnL：收盘价 - 开盘价（小所 + 大所）
        pnl = 0.0
        if pos.small_leg and small_close_result and small_close_result.success:
            if pos.direction == "long":
                pnl += (small_close_result.fill_price - pos.small_leg.entry_price) * pos.small_leg.size_base
            else:
                pnl += (pos.small_leg.entry_price - small_close_result.fill_price) * pos.small_leg.size_base
            pnl -= small_close_result.fee_usdt

        if pos.big_leg and big_close_result and big_close_result.success:
            if pos.direction == "long":
                pnl += (pos.big_leg.entry_price - big_close_result.fill_price) * pos.big_leg.size_base
            else:
                pnl += (big_close_result.fill_price - pos.big_leg.entry_price) * pos.big_leg.size_base
            pnl -= big_close_result.fee_usdt

        # 扣除开仓手续费
        if pos.small_leg:
            pnl -= pos.small_leg.fee_usdt
        if pos.big_leg:
            pnl -= pos.big_leg.fee_usdt

        pos.pnl_usdt = pnl

        # 从 tracker active_set 移除
        self._active_set.discard((pos.big_exchange, pos.small_exchange, pos.symbol))

        self._write_log(pos)
        logger.info(
            f"[pm] 平仓 {pos.id} | reason={reason} | pnl={pnl:+.4f} USDT"
            f" | hold={pos.hold_seconds:.1f}s | anomaly@close={close_anomaly_pct:.3f}%"
        )
        # 从内存中移除（平仓后不再需要，避免长期运行内存增长）
        self._positions.pop(pos_id, None)
        return pos

    # ─── 日志 ─────────────────────────────────────────────────────────────────

    def _ensure_log_header(self) -> None:
        if not TRADE_LOG.exists():
            with open(TRADE_LOG, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    # ── 仓位标识
                    "id", "symbol", "direction",
                    "big_exchange", "small_exchange",
                    # ── 时间
                    "open_time_utc", "close_time_utc", "hold_seconds",
                    # ── 价差
                    "open_anomaly_pct", "close_anomaly_pct",
                    # ── 平仓原因
                    "close_reason",
                    # ── 小所开仓腿
                    "small_open_order_id", "small_open_price",
                    "small_open_qty", "small_open_fee",
                    # ── 小所平仓腿
                    "small_close_order_id", "small_close_price", "small_close_fee",
                    # ── 大所开仓腿
                    "big_open_order_id", "big_open_price",
                    "big_open_qty", "big_open_fee",
                    # ── 大所平仓腿
                    "big_close_order_id", "big_close_price", "big_close_fee",
                    # ── 盈亏汇总
                    "gross_pnl", "total_fee", "net_pnl",
                ])

    def _write_log(self, pos: Position) -> None:
        from datetime import datetime, timezone

        def _utc(ts: float) -> str:
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        sl = pos.small_leg
        bl = pos.big_leg
        open_fee  = (sl.fee_usdt if sl else 0.0) + (bl.fee_usdt if bl else 0.0)
        close_fee = pos.small_close_fee + pos.big_close_fee
        gross_pnl = pos.pnl_usdt + open_fee + close_fee

        try:
            with open(TRADE_LOG, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    pos.id, pos.symbol, pos.direction,
                    pos.big_exchange, pos.small_exchange,
                    _utc(pos.open_time), _utc(pos.close_time), f"{pos.hold_seconds:.1f}",
                    f"{pos.open_anomaly_pct:.4f}", f"{pos.close_anomaly_pct:.4f}",
                    pos.close_reason,
                    # small open
                    sl.order_id if sl else "", f"{sl.entry_price:.6f}" if sl else "",
                    f"{sl.size_base:.6f}" if sl else "", f"{sl.fee_usdt:.4f}" if sl else "",
                    # small close
                    pos.small_close_order_id, f"{pos.small_close_price:.6f}", f"{pos.small_close_fee:.4f}",
                    # big open
                    bl.order_id if bl else "", f"{bl.entry_price:.6f}" if bl else "",
                    f"{bl.size_base:.6f}" if bl else "", f"{bl.fee_usdt:.4f}" if bl else "",
                    # big close
                    pos.big_close_order_id, f"{pos.big_close_price:.6f}", f"{pos.big_close_fee:.4f}",
                    # summary
                    f"{gross_pnl:.4f}", f"{open_fee + close_fee:.4f}", f"{pos.pnl_usdt:.4f}",
                ])
        except Exception as e:
            logger.error(f"[pm] 写入交易日志失败: {e}")
