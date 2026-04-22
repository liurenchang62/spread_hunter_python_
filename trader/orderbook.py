"""
订单薄缓存与滑点计算。

设计：
  - 拉取主网公开订单薄（无需鉴权），20档深度
  - TTL=2s：同一标的短时间多次触发只拉一次
  - walk_slippage：走单模拟，返回以 USDT 计的单程滑点
  - 失败时返回 None，由 cost_model 回退到 BBO 估算
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from clients.config import REST_BASE, to_exchange_fmt

logger = logging.getLogger("trader.ob")

# 每次拉取的深度档数（20档对小资金足够，权重/请求量也很小）
_DEPTH = 20
_TTL   = 2.0   # 秒，同一标的复用缓存


@dataclass
class OrderBook:
    exchange:   str
    symbol:     str
    bids: list[tuple[float, float]]   # (price, qty)，降序
    asks: list[tuple[float, float]]   # (price, qty)，升序
    fetched_at: float = 0.0


@dataclass
class OrderBookPair:
    small: Optional[OrderBook]
    big:   Optional[OrderBook]


class OrderBookCache:
    """
    并发拉取两腿订单薄，带 TTL 缓存。
    使用主网公开接口，不需要 API key。
    """

    def __init__(self, proxy: str = ""):
        self._cache:   dict[tuple, OrderBook] = {}
        self._proxy    = proxy
        self._session: Optional[aiohttp.ClientSession] = None

    def _px(self) -> dict:
        return {"proxy": self._proxy} if self._proxy else {}

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_pair(
        self,
        small_ex: str, small_sym: str,
        big_ex:   str, big_sym:   str,
    ) -> OrderBookPair:
        """并发拉取两腿订单薄，各自独立缓存。"""
        small_ob, big_ob = await asyncio.gather(
            self._get(small_ex, small_sym),
            self._get(big_ex,   big_sym),
            return_exceptions=True,
        )
        return OrderBookPair(
            small=small_ob if isinstance(small_ob, OrderBook) else None,
            big=big_ob     if isinstance(big_ob,   OrderBook) else None,
        )

    async def _get(self, exchange: str, symbol: str) -> Optional[OrderBook]:
        key    = (exchange, symbol)
        cached = self._cache.get(key)
        if cached and (time.time() - cached.fetched_at) < _TTL:
            return cached
        ob = await self._fetch(exchange, symbol)
        if ob:
            self._cache[key] = ob
        return ob

    async def _fetch(self, exchange: str, symbol: str) -> Optional[OrderBook]:
        try:
            if exchange == "binance":
                return await self._fetch_binance(symbol)
            elif exchange == "okx":
                return await self._fetch_okx(symbol)
            elif exchange == "gate":
                return await self._fetch_gate(symbol)
            elif exchange == "bitget":
                return await self._fetch_bitget(symbol)
        except Exception as e:
            logger.debug(f"[ob] {exchange} {symbol} 拉取失败: {e}")
        return None

    # ─── 各所拉取 ─────────────────────────────────────────────────────────────

    async def _fetch_binance(self, symbol: str) -> Optional[OrderBook]:
        # 公开接口，limit=20 权重=2，主网 URL
        base = REST_BASE["binance"]
        sess = await self._sess()
        async with sess.get(
            f"{base}/fapi/v1/depth",
            params={"symbol": symbol.upper(), "limit": _DEPTH},
            timeout=aiohttp.ClientTimeout(total=3), **self._px(),
        ) as r:
            data = await r.json()
        if r.status != 200:
            return None
        bids = [(float(p), float(q)) for p, q in data["bids"]]
        asks = [(float(p), float(q)) for p, q in data["asks"]]
        return OrderBook(exchange="binance", symbol=symbol,
                         bids=bids, asks=asks, fetched_at=time.time())

    async def _fetch_okx(self, symbol: str) -> Optional[OrderBook]:
        # 公开接口，sz=20，格式 [price, sz, ...]
        base    = REST_BASE["okx"]
        inst_id = to_exchange_fmt(symbol, "okx")   # BTC-USDT-SWAP
        sess    = await self._sess()
        async with sess.get(
            f"{base}/api/v5/market/books",
            params={"instId": inst_id, "sz": str(_DEPTH)},
            timeout=aiohttp.ClientTimeout(total=3), **self._px(),
        ) as r:
            data = await r.json()
        if data.get("code") != "0" or not data.get("data"):
            return None
        d    = data["data"][0]
        bids = [(float(x[0]), float(x[1])) for x in d["bids"]]
        asks = [(float(x[0]), float(x[1])) for x in d["asks"]]
        return OrderBook(exchange="okx", symbol=symbol,
                         bids=bids, asks=asks, fetched_at=time.time())

    async def _fetch_gate(self, symbol: str) -> Optional[OrderBook]:
        # 公开接口，格式 {p: price, s: size}，走主网
        base     = REST_BASE["gate"]
        contract = to_exchange_fmt(symbol, "gate")   # BTC_USDT
        sess     = await self._sess()
        async with sess.get(
            f"{base}/api/v4/futures/usdt/order_book",
            params={"contract": contract, "limit": _DEPTH, "with_id": "false"},
            timeout=aiohttp.ClientTimeout(total=3), **self._px(),
        ) as r:
            data = await r.json()
        if r.status != 200 or not isinstance(data, dict):
            return None
        bids = [(float(x["p"]), float(x["s"])) for x in data.get("bids", [])]
        asks = [(float(x["p"]), float(x["s"])) for x in data.get("asks", [])]
        return OrderBook(exchange="gate", symbol=symbol,
                         bids=bids, asks=asks, fetched_at=time.time())

    async def _fetch_bitget(self, symbol: str) -> Optional[OrderBook]:
        # 公开接口 v2，格式 [price, qty] 字符串，走主网
        base = REST_BASE["bitget"]
        sess = await self._sess()
        async with sess.get(
            f"{base}/api/v2/mix/market/orderbook",
            params={"symbol": symbol.upper(), "productType": "USDT-FUTURES",
                    "limit": str(_DEPTH)},
            timeout=aiohttp.ClientTimeout(total=3), **self._px(),
        ) as r:
            data = await r.json()
        if str(data.get("code", "")) != "00000" or not data.get("data"):
            return None
        d    = data["data"]
        bids = [(float(x[0]), float(x[1])) for x in d.get("bids", [])]
        asks = [(float(x[0]), float(x[1])) for x in d.get("asks", [])]
        return OrderBook(exchange="bitget", symbol=symbol,
                         bids=bids, asks=asks, fetched_at=time.time())


# ─── 走单滑点计算 ─────────────────────────────────────────────────────────────

def walk_slippage(side: str, levels: list[tuple[float, float]], budget_usdt: float) -> float:
    """
    模拟以市价单吃掉 budget_usdt 的流动性，返回单程滑点（USDT）。

    side: "buy"  → 吃 asks（升序），avg_fill > best_ask → 滑点为正
          "sell" → 吃 bids（降序），avg_fill < best_bid → 滑点为正

    思路：走单后的平均成交价 vs 最优价的差值 × 成交量
    """
    if not levels or budget_usdt <= 0:
        return 0.0

    best_price     = levels[0][0]
    remaining_usdt = budget_usdt
    total_qty      = 0.0
    total_cost     = 0.0

    for price, qty in levels:
        level_usdt = price * qty
        if level_usdt >= remaining_usdt:
            fill_qty    = remaining_usdt / price
            total_qty  += fill_qty
            total_cost += remaining_usdt
            remaining_usdt = 0.0
            break
        total_qty  += qty
        total_cost += level_usdt
        remaining_usdt -= level_usdt

    if total_qty <= 0:
        return 0.0

    avg_fill   = total_cost / total_qty
    ideal_cost = total_qty * best_price   # 若全在最优价成交的成本

    if side == "buy":
        # 实际花费 > 理想花费
        return max(0.0, total_cost - ideal_cost)
    else:
        # 实际收入 < 理想收入
        return max(0.0, ideal_cost - total_cost)
