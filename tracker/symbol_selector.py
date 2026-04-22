"""
标的筛选：在 ACTIVE_EXCHANGES 各所都有的 USDT-M 永续合约，按24h成交额排序取前N个。

流程：
  1. 从 Binance FAPI 拉 USDT-M 合约 + 24h 成交额（主网失败则回退测试网）
  2. 从其余所拉合约列表，构建各所可用标的集合
  3. 取各所交集，按 Binance 侧成交额排序，返回前 TOP_N 个标的
  4. 每 SYMBOL_REFRESH_H 小时刷新一次

返回的标的格式：内部格式 BTCUSDT（Binance 风格，大写，无分隔符）
"""

import asyncio
import logging
import time
import warnings
from typing import Optional

import requests
import urllib3

# Windows 上本地 CA 缺失导致 SSL 验证失败很常见，统一关掉警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from .config import TOP_N_SYMBOLS, MIN_VOLUME_USDT, SYMBOL_REFRESH_H
from clients import ACTIVE_EXCHANGES, BIG_EXCHANGES, SMALL_EXCHANGES, get_rest_url

logger = logging.getLogger("tracker.symbols")


def _get_rest_base(exchange: str) -> str:
    """始终使用主网 REST 地址拉取标的（信号源用主网数据）。"""
    return get_rest_url(exchange, testnet=False)


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def _get(url: str, params: dict = None, timeout: int = 10) -> Optional[dict | list]:
    """同步 HTTP GET，封装异常。供 asyncio.to_thread 调用。
    verify=False 绕过 Windows 常见的 SSL 本地证书问题。
    """
    try:
        r = requests.get(url, params=params, timeout=timeout, verify=False)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"GET {url} 失败: {e}")
        return None


# ─── 各交易所标的列表获取 ─────────────────────────────────────────────────────

def _binance_symbols_with_volume() -> dict[str, float]:
    """
    返回 {BTCUSDT: 24h_quote_volume, ...}
    只保留 USDT 永续合约且成交额 >= MIN_VOLUME_USDT 的标的。

    主网 fapi.binance.com 在部分国家/地区会返回 451，云服务器常见；
    失败时回退到期货测试网拉取（用于排序与交集，Demo 模式可正常跑）。
    """
    main_base = get_rest_url("binance", testnet=False)
    data = _get(f"{main_base}/fapi/v1/ticker/24hr")
    min_vol = MIN_VOLUME_USDT
    if not data:
        test_base = get_rest_url("binance", testnet=True)
        logger.warning(
            "Binance 主网 24h 行情不可用（常见：地区限制 451），改用测试网 %s",
            test_base,
        )
        data = _get(f"{test_base}/fapi/v1/ticker/24hr")
        # 测试网成交额远低于主网，不过滤下限以免交集为空
        min_vol = 0.0
    if not data:
        return {}
    result = {}
    for item in data:
        sym = item.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            vol = float(item.get("quoteVolume", 0))
        except (TypeError, ValueError):
            continue
        if vol >= min_vol:
            result[sym] = vol
    return result


def _okx_symbols() -> set[str]:
    """返回 OKX 可交易的 USDT 永续合约，内部格式如 BTCUSDT。"""
    data = _get(f"{_get_rest_base('okx')}/api/v5/public/instruments", {"instType": "SWAP"})
    if not data or data.get("code") != "0":
        return set()
    result = set()
    for item in data.get("data", []):
        inst_id = item.get("instId", "")   # 格式: BTC-USDT-SWAP
        state   = item.get("state", "")
        if inst_id.endswith("-USDT-SWAP") and state == "live":
            base = inst_id.replace("-USDT-SWAP", "")
            result.add(f"{base}USDT")
    return result


def _gate_symbols() -> set[str]:
    """返回 Gate USDT 永续合约，内部格式如 BTCUSDT。"""
    data = _get(f"{_get_rest_base('gate')}/api/v4/futures/usdt/contracts")
    if not data:
        return set()
    result = set()
    for item in data:
        name = item.get("name", "")        # 格式: BTC_USDT
        in_delisting = item.get("in_delisting", True)
        if name.endswith("_USDT") and not in_delisting:
            base = name.replace("_USDT", "")
            result.add(f"{base}USDT")
    return result


def _bitget_symbols() -> set[str]:
    """返回 Bitget USDT-M 合约标的，内部格式如 BTCUSDT。"""
    data = _get(
        f"{_get_rest_base('bitget')}/api/v2/mix/market/contracts",
        {"productType": "USDT-FUTURES"},
    )
    if not data or str(data.get("code", "")) != "00000":
        return set()
    result = set()
    for item in data.get("data", []):
        sym = item.get("symbol", "")      # 格式: BTCUSDT
        status = item.get("symbolStatus", "")
        if sym.endswith("USDT") and status == "normal":
            result.add(sym)
    return result


# ─── 主逻辑 ───────────────────────────────────────────────────────────────────

# ─── 交易所标获取函数字典 ─────────────────────────────────────────────────────
_SYMBOL_FETCHERS = {
    "binance": _binance_symbols_with_volume,
    "okx":     _okx_symbols,
    "gate":    _gate_symbols,
    "bitget":  _bitget_symbols,
}


async def fetch_common_symbols() -> list[str]:
    """
    异步调度，返回所有参与交易所（ACTIVE_EXCHANGES）共有的标的，
    按 Binance 24h 成交额从大到小排序，最多返回 TOP_N_SYMBOLS 个。
    """
    logger.info(f"开始拉取各交易所标的列表…（参与交易所: {ACTIVE_EXCHANGES}）")

    # 动态构建要查询的交易所列表
    tasks = []
    exchange_order = []  # 记录顺序以便解析结果

    # Binance 必须第一个（作为成交额基准）
    if "binance" in ACTIVE_EXCHANGES:
        tasks.append(asyncio.to_thread(_binance_symbols_with_volume))
        exchange_order.append("binance")

    # 其他交易所
    for ex in ACTIVE_EXCHANGES:
        if ex != "binance" and ex in _SYMBOL_FETCHERS:
            tasks.append(asyncio.to_thread(_SYMBOL_FETCHERS[ex]))
            exchange_order.append(ex)

    # 并发调用（都是 IO 操作）
    results = await asyncio.gather(*tasks)

    # 解析结果
    result_map = dict(zip(exchange_order, results))
    bn_vol = result_map.get("binance", {})

    # 日志输出各所标的数
    counts_info = " | ".join([f"{ex}={len(result_map.get(ex, set() if ex != 'binance' else {}))}" for ex in exchange_order])
    logger.info(f"各所标的数: {counts_info}")

    # 计算交集（所有参与交易所共有的标的）
    symbol_sets = []
    for ex in exchange_order:
        if ex == "binance":
            symbol_sets.append(set(bn_vol.keys()))
        else:
            symbol_sets.append(set(result_map.get(ex, set())))

    if not symbol_sets:
        logger.warning("没有可用的交易所标的数据")
        return []

    common = symbol_sets[0]
    for s in symbol_sets[1:]:
        common &= s

    # 过滤测试网不支持的币种
    from clients.config import TESTNET_SYMBOL_BLACKLIST
    common = common - TESTNET_SYMBOL_BLACKLIST
    
    # 按 Binance 成交额排序，取前 N
    ranked = sorted(common, key=lambda s: bn_vol.get(s, 0), reverse=True)
    selected = ranked[:TOP_N_SYMBOLS]

    n_exchanges = len(exchange_order)
    logger.info(f"筛选完成：{n_exchanges}所共同标的 {len(common)} 个（已排除黑名单 {len(TESTNET_SYMBOL_BLACKLIST)} 个），选用 {len(selected)} 个")
    if selected:
        preview = ", ".join(selected[:10])
        logger.info(f"前10: {preview}{'…' if len(selected) > 10 else ''}")

    return selected


class SymbolSelector:
    """
    持有当前的标的列表，并定期刷新。
    tracker.py 持有一个实例，启动时调用 start()，之后访问 .symbols。
    """

    def __init__(self):
        self.symbols: list[str] = []
        self._refresh_interval = SYMBOL_REFRESH_H * 3600
        self._last_refresh: float = 0.0

    async def start(self) -> list[str]:
        """首次加载。失败时返回空列表（后续可重试）。"""
        self.symbols = await fetch_common_symbols()
        self._last_refresh = time.time()
        return self.symbols

    async def maybe_refresh(self) -> bool:
        """如果距上次刷新超过 SYMBOL_REFRESH_H 小时，则重新拉取。返回是否发生了刷新。"""
        if time.time() - self._last_refresh < self._refresh_interval:
            return False
        new = await fetch_common_symbols()
        if new:
            self.symbols = new
            self._last_refresh = time.time()
            return True
        return False
