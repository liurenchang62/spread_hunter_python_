"""
市场信息缓存：合约规格（lot size）、手续费、资金费率。

每 MARKET_INFO_REFRESH_H 小时自动刷新一次。
所有接口均使用公开 REST（无需鉴权），taker 费率暂用已知值。

SymbolInfo.qty_step / min_qty 统一用「目标币数量（base coin）」表示，
exchange_client 在下单时负责将 base coin 数量转换为各所的合约张数。
"""

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field

import aiohttp

from clients.config import REST_BASE, TESTNET_REST_BASE
from trader.config import MARKET_INFO_REFRESH_H, LIVE_TRADING_ON

logger = logging.getLogger("trader.market_info")

# ─── 已知 taker 费率（VIP0，USDT-M 永续，吃单）─────────────────────────────
# 格式：小数（0.0005 = 0.05%）
DEFAULT_TAKER_FEES: dict[str, float] = {
    "binance": 0.0005,   # 0.05%
    "okx":     0.0005,   # 0.05%
    "gate":    0.00075,  # 0.075%
    "bitget":  0.0006,   # 0.06%
}


# ─── 数据结构 ─────────────────────────────────────────────────────────────────

@dataclass
class SymbolInfo:
    """
    某交易所某合约的规格信息。
    qty_step / min_qty 均以 base coin（目标币）为单位。
    native_ct_val：每张合约对应的 base coin 数量（供 exchange_client 转换张数用）。
      Binance：1.0（qty 直接用 base coin）
      OKX    ：ctVal（如 BTC-USDT-SWAP 为 0.01）
      Gate   ：quanto_multiplier（如 BTC_USDT 为 0.0001）
      Bitget ：sizeMultiplier（最小单位，如 0.001 BTC）
    """
    exchange:     str
    symbol:       str    # 内部格式，如 BTCUSDT
    qty_step:     float  # 最小下单步进（base coin）
    min_qty:      float  # 最小下单量（base coin）
    native_ct_val: float = 1.0


@dataclass
class MarketInfo:
    """全局缓存对象，由 Trader 持有。"""
    # symbol_info[(exchange, symbol)] → SymbolInfo
    symbol_info:   dict[tuple, SymbolInfo] = field(default_factory=dict)
    # taker_fee[exchange] → float
    taker_fee:     dict[str, float]        = field(default_factory=lambda: dict(DEFAULT_TAKER_FEES))
    # funding_rate[(exchange, symbol)] → float（8h 资金费率，小数）
    funding_rate:  dict[tuple, float]      = field(default_factory=dict)
    _last_refresh: float                   = 0.0

    # ── 查询接口 ──────────────────────────────────────────────────────────────

    def get_symbol_info(self, exchange: str, symbol: str) -> SymbolInfo | None:
        return self.symbol_info.get((exchange, symbol))

    def get_taker_fee(self, exchange: str) -> float:
        return self.taker_fee.get(exchange, DEFAULT_TAKER_FEES.get(exchange, 0.001))

    def get_funding_rate(self, exchange: str, symbol: str) -> float:
        """返回当前 8h 资金费率（小数），未知时返回 0.0003（0.03% 保守估计）。"""
        return self.funding_rate.get((exchange, symbol), 0.0003)

    def calc_target_qty(
        self,
        exchange: str,
        symbol: str,
        budget_usdt: float,
        ref_price: float,
    ) -> float:
        """
        给定单腿资金预算（USDT）和参考价格，返回最大可买的 base coin 数量。
        结果已按 qty_step 向下取整，小于 min_qty 则返回 0。
        """
        if ref_price <= 0:
            return 0.0
        info = self.symbol_info.get((exchange, symbol))
        if info is None or info.qty_step <= 0:
            # 无规格数据：根据价格确定精度（避免过多小数位导致Binance报错）
            # 使用 ceil 确保名义价值 >= budget（满足最小名义价值要求）
            raw = budget_usdt / ref_price
            if ref_price < 0.1:
                decimal_places, step = 0, 1.0
            elif ref_price < 1.0:
                decimal_places, step = 1, 0.1
            elif ref_price < 10.0:
                decimal_places, step = 2, 0.01
            elif ref_price < 100.0:
                decimal_places, step = 3, 0.001
            else:
                decimal_places, step = 4, 0.0001
            # 向上取整确保名义价值 >= budget
            qty = math.ceil(raw / step) * step
            return round(qty, decimal_places)

        raw = budget_usdt / ref_price
        # 根据价格确定合理的小数精度（避免返回过多小数位导致Binance报错）
        if ref_price < 0.1:
            decimal_places = 0
        elif ref_price < 1.0:
            decimal_places = 1
        elif ref_price < 10.0:
            decimal_places = 2
        elif ref_price < 100.0:
            decimal_places = 3
        else:
            decimal_places = 4
        # 向上取整确保名义价值 >= budget（满足最小名义价值要求）
        qty = math.ceil(raw / info.qty_step) * info.qty_step
        qty = round(qty, decimal_places)
        return qty if qty >= info.min_qty else 0.0

    def needs_refresh(self) -> bool:
        return (time.time() - self._last_refresh) >= MARKET_INFO_REFRESH_H * 3600


# ─── 异步拉取函数 ─────────────────────────────────────────────────────────────

def _px(proxy: str) -> dict:
    return {"proxy": proxy} if proxy else {}


async def _fetch_binance_info(
    session: aiohttp.ClientSession,
    mi: MarketInfo,
    symbols: set[str],
    proxy: str = "",
    live: bool = False,
):
    """拉取 Binance USDT-M 合约规格（LOT_SIZE）和当前资金费率。
    注意：测试网和主网的合约规格可能不同，根据 live 参数选择来源。
    """
    from clients.config import TESTNET_REST_BASE
    # 根据 live 参数选择 base URL，确保规格与下单环境一致
    base = REST_BASE["binance"] if live else TESTNET_REST_BASE["binance"]
    try:
        async with session.get(
            f"{base}/fapi/v1/exchangeInfo", ssl=False,
            timeout=aiohttp.ClientTimeout(total=10), **_px(proxy),
        ) as r:
            data = await r.json()
        for s in data.get("symbols", []):
            sym = s.get("symbol", "").upper()
            if sym not in symbols:
                continue
            qty_step = 0.0
            min_qty  = 0.0
            for f in s.get("filters", []):
                if f["filterType"] == "LOT_SIZE":
                    qty_step = float(f["stepSize"])
                    min_qty  = float(f["minQty"])
                    break
            if qty_step > 0:
                mi.symbol_info[("binance", sym)] = SymbolInfo(
                    exchange="binance", symbol=sym,
                    qty_step=qty_step, min_qty=min_qty,
                    native_ct_val=1.0,  # Binance qty 直接是 base coin
                )
        logger.info(f"[market_info] Binance 合约规格已更新，共 {len(symbols)} 个标的")
    except Exception as e:
        logger.warning(f"[market_info] Binance exchangeInfo 失败: {e}")

    # 资金费率
    try:
        async with session.get(
            f"{base}/fapi/v1/premiumIndex", ssl=False,
            timeout=aiohttp.ClientTimeout(total=10), **_px(proxy),
        ) as r:
            data = await r.json()
        for item in data:
            sym = item.get("symbol", "").upper()
            if sym in symbols:
                fr = float(item.get("lastFundingRate", 0))
                mi.funding_rate[("binance", sym)] = fr
    except Exception as e:
        logger.warning(f"[market_info] Binance fundingRate 失败: {e}")


async def _fetch_okx_info(
    session: aiohttp.ClientSession,
    mi: MarketInfo,
    symbols: set[str],
    proxy: str = "",
):
    """拉取 OKX USDT-SWAP 合约规格（ctVal, lotSz）和当前资金费率。"""
    base = REST_BASE["okx"]
    try:
        async with session.get(
            f"{base}/api/v5/public/instruments",
            params={"instType": "SWAP"},
            ssl=False, timeout=aiohttp.ClientTimeout(total=10), **_px(proxy),
        ) as r:
            data = await r.json()
        for inst in data.get("data", []):
            inst_id = inst.get("instId", "")
            if not inst_id.endswith("-USDT-SWAP"):
                continue
            sym = inst_id.replace("-USDT-SWAP", "") + "USDT"
            if sym not in symbols:
                continue
            ct_val  = float(inst.get("ctVal",  "1") or "1")   # base coins per contract
            lot_sz  = float(inst.get("lotSz",  "1") or "1")   # min contract step
            min_sz  = float(inst.get("minSz",  "1") or "1")   # min order size (contracts)
            qty_step = lot_sz * ct_val
            min_qty  = min_sz * ct_val
            mi.symbol_info[("okx", sym)] = SymbolInfo(
                exchange="okx", symbol=sym,
                qty_step=qty_step, min_qty=min_qty,
                native_ct_val=ct_val,
            )
        logger.info("[market_info] OKX 合约规格已更新")
    except Exception as e:
        logger.warning(f"[market_info] OKX instruments 失败: {e}")

    # 资金费率（逐个查询，只查监控中的标的）
    fetched = 0
    for sym in list(symbols)[:20]:   # 限制并发请求数
        inst_id = sym[:-4] + "-USDT-SWAP"
        try:
            async with session.get(
                f"{base}/api/v5/public/funding-rate",
                params={"instId": inst_id},
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **_px(proxy),
            ) as r:
                d = await r.json()
            items = d.get("data", [])
            if items:
                fr = float(items[0].get("fundingRate", 0))
                mi.funding_rate[("okx", sym)] = fr
                fetched += 1
        except Exception:
            pass
    logger.info(f"[market_info] OKX 资金费率已更新 {fetched} 个")


async def _fetch_gate_info(
    session: aiohttp.ClientSession,
    mi: MarketInfo,
    symbols: set[str],
    proxy: str = "",
):
    """拉取 Gate USDT 永续合约规格（quanto_multiplier）和资金费率。"""
    base = REST_BASE["gate"]
    try:
        async with session.get(
            f"{base}/api/v4/futures/usdt/contracts",
            ssl=False, timeout=aiohttp.ClientTimeout(total=10), **_px(proxy),
        ) as r:
            data = await r.json()
        for c in data:
            name = c.get("name", "")   # e.g. "BTC_USDT"
            sym = name.replace("_USDT", "") + "USDT" if name.endswith("_USDT") else None
            if sym not in symbols:
                continue
            # quanto_multiplier = base coins per contract
            ct_val   = float(c.get("quanto_multiplier", "0") or "0")
            min_size = int(c.get("order_size_min", 1))
            if ct_val <= 0:
                continue
            qty_step = ct_val          # 1 contract = ct_val base coins
            min_qty  = min_size * ct_val
            mi.symbol_info[("gate", sym)] = SymbolInfo(
                exchange="gate", symbol=sym,
                qty_step=qty_step, min_qty=min_qty,
                native_ct_val=ct_val,
            )
        logger.info("[market_info] Gate 合约规格已更新")
    except Exception as e:
        logger.warning(f"[market_info] Gate contracts 失败: {e}")

    # 资金费率（批量）
    try:
        async with session.get(
            f"{base}/api/v4/futures/usdt/funding_rate",
            ssl=False, timeout=aiohttp.ClientTimeout(total=10), **_px(proxy),
        ) as r:
            data = await r.json()
        if isinstance(data, list):
            for item in data:
                contract = item.get("contract", "")
                sym = contract.replace("_USDT", "") + "USDT" if contract.endswith("_USDT") else None
                if sym and sym in symbols:
                    fr = float(item.get("r", 0))
                    mi.funding_rate[("gate", sym)] = fr
    except Exception as e:
        logger.warning(f"[market_info] Gate fundingRate 失败: {e}")


async def _fetch_bitget_info(
    session: aiohttp.ClientSession,
    mi: MarketInfo,
    symbols: set[str],
    proxy: str = "",
):
    """拉取 Bitget USDT-M 合约规格和资金费率（API v2）。"""
    base = REST_BASE["bitget"]

    # 合约规格
    try:
        async with session.get(
            f"{base}/api/v2/mix/market/contracts",
            params={"productType": "USDT-FUTURES"},
            ssl=False, timeout=aiohttp.ClientTimeout(total=10), **_px(proxy),
        ) as r:
            data = await r.json()
        for c in (data.get("data") or []):
            sym_raw = c.get("symbol", "")
            sym = sym_raw.upper()
            if not sym.endswith("USDT"):
                continue
            if sym not in symbols:
                continue
            step  = float(c.get("sizeMultiplier", "0.001") or "0.001")
            min_q = float(c.get("minTradeNum",    "0.001") or "0.001")
            mi.symbol_info[("bitget", sym)] = SymbolInfo(
                exchange="bitget", symbol=sym,
                qty_step=step, min_qty=min_q,
                native_ct_val=1.0,   # Bitget qty 直接是 base coin
            )
        logger.info("[market_info] Bitget 合约规格已更新")
    except Exception as e:
        logger.warning(f"[market_info] Bitget contracts 失败: {e}")

    # 逐个查资金费率（v2 当前费率接口）
    fetched = 0
    for sym in list(symbols)[:20]:
        try:
            async with session.get(
                f"{base}/api/v2/mix/market/current-fund-rate",
                params={"symbol": sym, "productType": "USDT-FUTURES"},
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **_px(proxy),
            ) as r:
                d = await r.json()
            items = d.get("data") or []
            if items:
                fr = float(items[0].get("fundingRate", 0))
                mi.funding_rate[("bitget", sym)] = fr
                fetched += 1
        except Exception:
            pass
    logger.info(f"[market_info] Bitget 资金费率已更新 {fetched} 个")


# ─── 主入口 ───────────────────────────────────────────────────────────────────

async def refresh_market_info(
    mi: MarketInfo,
    symbols: set[str],
    proxy: str = "",
    live: bool = False,
) -> None:
    """
    并发拉取4所的合约规格 + 资金费率，写入 mi 对象。
    symbols：内部格式，如 {"BTCUSDT", "ETHUSDT", ...}
    proxy：HTTP 代理地址，国内访问 OKX/Bitget 需要传入。
    live：是否实盘模式，影响 Binance 合约规格来源（主网 vs 测试网）
    """
    logger.info(f"[market_info] 开始刷新市场信息（{len(symbols)} 个标的）…")
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        await asyncio.gather(
            _fetch_binance_info(session, mi, symbols, proxy, live),
            _fetch_okx_info(session, mi, symbols, proxy),
            _fetch_gate_info(session, mi, symbols, proxy),
            _fetch_bitget_info(session, mi, symbols, proxy),
            return_exceptions=True,
        )
    mi._last_refresh = time.time()
    logger.info(
        f"[market_info] 刷新完成 | 规格: {len(mi.symbol_info)} 条 | "
        f"资金费: {len(mi.funding_rate)} 条"
    )
