"""
5所 WebSocket 行情接入。每个交易所一个独立的 async task，自动重连。

交易所配置从 clients 模块导入：
    from clients import WS_URLS, ALL_EXCHANGES, to_exchange_fmt, from_raw_symbol

支持交易所（全部永续合约 / USDT-M）：
  - Binance   fstream combined bookTicker
  - OKX       books5 channel (SWAP)
  - Gate      futures.book_ticker channel
  - Bitget    books1 channel (USDT-FUTURES)
  - HTX       linear-swap-ws BBO (api.hbdm.com，非现货)

内部标的格式：BTCUSDT（大写，无分隔符）
"""

import asyncio
import gzip
import json
import logging
import time
from collections.abc import Callable
from typing import Optional

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:
    raise ImportError("请先安装依赖: pip install websockets")

try:
    import orjson
    def _loads(s) -> dict: return orjson.loads(s)
    def _dumps(d) -> str:  return orjson.dumps(d).decode()
except ImportError:
    def _loads(s) -> dict: return json.loads(s)
    def _dumps(d) -> str:  return json.dumps(d)

from clients import ALL_EXCHANGES, to_exchange_fmt, from_raw_symbol, get_ws_url
from .models import Tick

logger = logging.getLogger("tracker.ws")

TickCallback = Callable[[Tick], None]


# ─── 解析函数（每所一个） ─────────────────────────────────────────────────────

def _parse(exchange: str, raw, symbol_set: set[str]) -> Optional[Tick]:
    """
    解析原始 WS 消息，返回 Tick 或 None。
    raw 可能是 str 或 bytes（HTX gzip）。
    symbol_set 是当前监控的内部标的集合，用于过滤不感兴趣的标的。
    """
    # HTX gzip 解压
    if isinstance(raw, bytes):
        try:
            raw = gzip.decompress(raw)
        except Exception:
            return None

    try:
        d = _loads(raw)
    except Exception:
        return None

    try:
        if exchange == "binance":
            # combined stream: {"stream":"btcusdt@bookTicker","data":{...}}
            dd = d.get("data", d)
            s  = dd.get("s", "")
            sym = from_raw_symbol(s, "binance")
            if sym and sym in symbol_set:
                return Tick("binance", sym, float(dd["b"]), float(dd["a"]))

        elif exchange == "okx":
            # {"arg":{"channel":"books5","instId":"BTC-USDT-SWAP"},"data":[{"bids":[[px,sz,0,n]],"asks":...}]}
            arg  = d.get("arg", {})
            data = d.get("data")
            if data and arg.get("channel") in ("books5", "bbo-tbt"):
                sym = from_raw_symbol(arg.get("instId", ""), "okx")
                if sym and sym in symbol_set:
                    bk  = data[0]
                    bid = float(bk["bids"][0][0])
                    ask = float(bk["asks"][0][0])
                    return Tick("okx", sym, bid, ask)

        elif exchange == "gate":
            # {"channel":"futures.book_ticker","event":"update","result":{"s":"BTC_USDT","b":"...","a":"..."}}
            result = d.get("result")
            if result:
                sym = from_raw_symbol(result.get("s", result.get("contract", "")), "gate")
                if sym and sym in symbol_set:
                    b = float(result.get("b", 0) or 0)
                    a = float(result.get("a", 0) or 0)
                    if b > 0 and a > 0:
                        return Tick("gate", sym, b, a)

        elif exchange == "bitget":
            # {"action":"snapshot","arg":{"channel":"books1","instId":"BTCUSDT"},"data":[{"bids":[[px,sz]],"asks":...}]}
            arg  = d.get("arg", {})
            data = d.get("data")
            if data and arg.get("channel") == "books1":
                sym = from_raw_symbol(arg.get("instId", ""), "bitget")
                if sym and sym in symbol_set:
                    bk  = data[0]
                    bis = bk.get("bids", [])
                    ais = bk.get("asks", [])
                    if bis and ais:
                        return Tick("bitget", sym, float(bis[0][0]), float(ais[0][0]))

        elif exchange == "htx":
            # {"ch":"market.BTC-USDT.bbo","tick":{"bid":[px,sz],"ask":[px,sz],...}}
            ch = d.get("ch", "")
            td = d.get("tick")
            if td and "bbo" in ch:
                # 从 ch 里提取合约代码: "market.BTC-USDT.bbo" → "BTC-USDT"
                parts = ch.split(".")
                raw_sym = parts[1] if len(parts) >= 2 else ""
                sym = from_raw_symbol(raw_sym, "htx")
                if sym and sym in symbol_set:
                    # linear-swap 返回 [price, size] 数组，spot 返回 float，两种都兼容
                    bid_raw = td.get("bid", 0)
                    ask_raw = td.get("ask", 0)
                    bid = float(bid_raw[0]) if isinstance(bid_raw, (list, tuple)) else float(bid_raw)
                    ask = float(ask_raw[0]) if isinstance(ask_raw, (list, tuple)) else float(ask_raw)
                    if bid > 0 and ask > 0:
                        return Tick("htx", sym, bid, ask)

    except (KeyError, IndexError, ValueError, TypeError):
        pass

    return None


# ─── 订阅消息构建 ─────────────────────────────────────────────────────────────

def _build_sub(exchange: str, symbols: list[str]) -> list[str] | str | None:
    """返回需要发送的订阅消息（字符串或字符串列表）；Binance 不需要。"""
    if exchange == "binance":
        return None   # 直接拼在 URL 里

    if exchange == "okx":
        args = [{"channel": "books5", "instId": to_exchange_fmt(s, "okx")} for s in symbols]
        return _dumps({"op": "subscribe", "args": args})

    if exchange == "gate":
        payload = [to_exchange_fmt(s, "gate") for s in symbols]
        return _dumps({
            "time": int(time.time()),
            "channel": "futures.book_ticker",
            "event": "subscribe",
            "payload": payload,
        })

    if exchange == "bitget":
        args = [
            {"instType": "USDT-FUTURES", "channel": "books1", "instId": to_exchange_fmt(s, "bitget")}
            for s in symbols
        ]
        return _dumps({"op": "subscribe", "args": args})

    if exchange == "htx":
        # HTX 每个标的单独一条订阅消息
        msgs = []
        for s in symbols:
            contract = to_exchange_fmt(s, "htx")
            msgs.append(_dumps({"sub": f"market.{contract}.bbo", "id": f"bbo_{s}"}))
        return msgs

    return None


def _build_ws_url(exchange: str, symbols: list[str]) -> str:
    """Binance 把所有标的拼到 URL，其他交易所直接返回 base URL。"""
    # 行情订阅使用主网（测试网行情数据不足）
    base = get_ws_url(exchange, testnet=False)
    if exchange == "binance":
        streams = "/".join(f"{s.lower()}@bookTicker" for s in symbols)
        return f"{base}?streams={streams}"
    return base


# ─── 心跳处理 ─────────────────────────────────────────────────────────────────

async def _heartbeat_loop(exchange: str, ws, interval: int = 20):
    """
    OKX / Bitget：每 20s 发一次文本 "ping"。
    Binance / Gate：WS 协议级 ping 由 websockets 库自动处理，不需要这里管。
    HTX：服务端主动推 {"ping":ts}，在 _run 里处理，这里不用额外发。
    """
    if exchange not in ("okx", "bitget"):
        return
    while True:
        await asyncio.sleep(interval)
        try:
            await ws.send("ping")
        except Exception:
            break


# ─── 单交易所 WS 任务 ─────────────────────────────────────────────────────────

async def _run_exchange(
    exchange: str,
    symbols: list[str],
    symbol_set: set[str],
    callback: TickCallback,
    connected: set[str],
    stop_event: asyncio.Event,
    reconnect_cb=None,          # Optional[Callable[[str], None]]
):
    """单个交易所的 WebSocket 主循环，断线后指数退避重连。"""
    url     = _build_ws_url(exchange, symbols)
    sub_msg = _build_sub(exchange, symbols)
    retry   = 0

    while not stop_event.is_set():
        try:
            async with websockets.connect(
                url,
                ping_interval=20,
                ping_timeout=10,
                max_size=2 ** 21,   # 2MB
                compression=None,   # 手动解 gzip（HTX）
                open_timeout=10,
            ) as ws:
                was_connected = exchange in connected
                retry = 0
                connected.add(exchange)
                logger.info(f"[{exchange}] {'重新连接' if was_connected else '已连接'}")
                if reconnect_cb is not None:
                    try:
                        reconnect_cb(exchange)
                    except Exception:
                        pass

                # 发送订阅消息
                if sub_msg:
                    msgs = sub_msg if isinstance(sub_msg, list) else [sub_msg]
                    for m in msgs:
                        await ws.send(m)
                        await asyncio.sleep(0.02)   # 避免发太快被限流

                # 启动心跳（仅 OKX / Bitget）
                hb_task = asyncio.create_task(_heartbeat_loop(exchange, ws))

                try:
                    async for raw in ws:
                        if stop_event.is_set():
                            break

                        # HTX 心跳：服务端推 {"ping": ts}，需要回 {"pong": ts}
                        if exchange == "htx":
                            try:
                                data = raw
                                if isinstance(raw, bytes):
                                    try:
                                        data = gzip.decompress(raw)
                                    except Exception:
                                        pass
                                d = _loads(data)
                                if "ping" in d:
                                    await ws.send(_dumps({"pong": d["ping"]}))
                                    continue
                            except Exception:
                                pass

                        tick = _parse(exchange, raw, symbol_set)
                        if tick:
                            callback(tick)

                finally:
                    hb_task.cancel()

        except (ConnectionClosed, OSError, asyncio.TimeoutError) as e:
            connected.discard(exchange)
            retry += 1
            wait = min(2 ** retry, 60)
            logger.warning(f"[{exchange}] 断线({type(e).__name__})，{wait}s 后重连 (第{retry}次)")
            await asyncio.sleep(wait)

        except Exception as e:
            connected.discard(exchange)
            retry += 1
            wait = min(2 ** retry, 60)
            logger.error(f"[{exchange}] 异常: {e}，{wait}s 后重连")
            await asyncio.sleep(wait)

    connected.discard(exchange)
    logger.info(f"[{exchange}] 已停止")


# ─── 对外接口 ─────────────────────────────────────────────────────────────────

class WSFeed:
    """
    管理5个交易所的 WebSocket 连接。
    使用方式：
        feed = WSFeed(symbols, on_tick_callback)
        await feed.start()          # 非阻塞，返回后各连接在后台运行
        await feed.stop()
    """

    def __init__(self, symbols: list[str], callback: TickCallback,
                 reconnect_cb=None):
        self.symbols      = symbols
        self.symbol_set   = set(symbols)
        self.callback     = callback
        self.reconnect_cb = reconnect_cb   # Optional[Callable[[str], None]]
        self.connected: set[str] = set()
        self._stop      = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        """为每个交易所启动一个后台 task。"""
        self._stop.clear()
        for ex in ALL_EXCHANGES:
            t = asyncio.create_task(
                _run_exchange(ex, self.symbols, self.symbol_set,
                              self.callback, self.connected, self._stop,
                              self.reconnect_cb),
                name=f"ws_{ex}",
            )
            self._tasks.append(t)
        logger.info(f"WSFeed 已启动，监控 {len(self.symbols)} 个标的，{len(ALL_EXCHANGES)} 所")

    async def stop(self):
        """通知所有 task 退出，等待它们结束。"""
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("WSFeed 已停止")

    def update_symbols(self, new_symbols: list[str]):
        """
        标的列表更新（目前实现：记录新列表，下次重连时生效）。
        如需热重载，可在此取消并重建 task。
        """
        self.symbols    = new_symbols
        self.symbol_set = set(new_symbols)
        logger.info(f"标的列表已更新为 {len(new_symbols)} 个，下次重连后生效")

    @property
    def n_connected(self) -> int:
        return len(self.connected)
