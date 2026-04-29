"""
各交易所 REST 下单客户端（测试网 / 主网双模式）。

统一接口：
    result = await client.place_order(symbol, side, target_qty, ref_price, symbol_info)

target_qty：base coin 数量（目标币，统一单位）
symbol_info：来自 market_info，包含 native_ct_val 供各所转换张数

side: "buy" | "sell"
"""

import base64
import hashlib
import hmac
import json
import logging
import math
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import aiohttp

from clients import get_rest_url

logger = logging.getLogger("trader.client")


# ─── 下单结果 ─────────────────────────────────────────────────────────────────

@dataclass
class OrderResult:
    success:    bool
    order_id:   str   = ""
    fill_price: float = 0.0
    fill_size:  float = 0.0   # base coin 数量
    fee_usdt:   float = 0.0
    error:      str   = ""


# ─── API Key 加载 ────────────────────────────────────────────────────────────

def _load_keys(live: bool = False) -> dict[str, dict]:
    """加载 API Key（根据 live 参数选择实盘或模拟盘）。"""
    keys: dict[str, dict] = {}
    if live:
        from clients.api_keys_live import get_live_keys
        getter = get_live_keys
    else:
        from clients.api_keys_demo import get_demo_keys
        getter = get_demo_keys
    for ex in ["binance", "okx", "gate", "bitget"]:
        k = getter(ex)
        if k and k.get("key"):
            keys[ex] = k
    logger.info(f"[trader.client] API Key 已加载（live={live}）: {list(keys.keys())}")
    return keys


# ─── 工具：base coin → 各所合约张数 ────────────────────────────────────────

def _to_contracts(target_qty: float, ct_val: float) -> int:
    """base coin 数量 → 合约张数（向下取整）。"""
    if ct_val <= 0:
        return 0
    return max(1, math.floor(target_qty / ct_val))


# ─── 基类 ─────────────────────────────────────────────────────────────────────

class BaseClient:
    exchange: str = ""

    def __init__(self, live: bool, keys: dict, proxy: str = ""):
        self.live  = live
        self.keys  = keys
        self.base  = get_rest_url(self.exchange, testnet=not live)
        self.proxy = proxy or ""
        self._session: Optional[aiohttp.ClientSession] = None

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    def _px(self) -> dict:
        """返回代理参数 kwargs，无代理时为空 dict。"""
        return {"proxy": self.proxy} if self.proxy else {}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def place_order(
        self,
        symbol: str,
        side: str,
        target_qty: float,
        ref_price: float,
        symbol_info=None,    # SymbolInfo | None
        reduce_only: bool = False,
    ) -> OrderResult:
        raise NotImplementedError

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        target_qty: float,
        limit_price: float,
        symbol_info=None,
        reduce_only: bool = False,
    ) -> OrderResult:
        raise NotImplementedError

    async def get_balance(self) -> float:
        raise NotImplementedError

    async def get_positions(self, symbol: str = "") -> list[dict]:
        raise NotImplementedError

    async def get_open_orders(self, symbol: str = "") -> list[dict]:
        raise NotImplementedError

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        raise NotImplementedError

    async def transfer_to_spot(self, amount: float) -> bool:
        """将期货账户 USDT 划转至现货/资金账户（提币前置步骤）。"""
        raise NotImplementedError

    async def transfer_to_futures(self, amount: float) -> bool:
        """将现货/资金账户 USDT 划转至期货账户（到账后置步骤）。"""
        raise NotImplementedError

    async def get_spot_balance(self) -> float:
        """查询现货/资金账户 USDT 可用余额（用于再平衡）。"""
        raise NotImplementedError

    async def get_total_balance(self) -> float:
        """
        查询期货账户 USDT 总权益（含已用保证金 + 未实现盈亏）。
        与 get_balance()（仅可用余额）配合用于整体流动性比计算：
            cash_ratio = (get_balance() + get_spot_balance()) /
                         (get_total_balance() + get_spot_balance())
        """
        raise NotImplementedError

    async def get_earn_balance(self) -> float:
        """查询活期理财 USDT 余额（只读，不赎回）。"""
        return 0.0

    async def redeem_earn(self) -> float:
        """从活期理财账户赎回 USDT 到现货/资金账户。返回赎回金额，0 表示无持仓或不支持。"""
        return 0.0

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """设置合约杠杆（尽力而为，失败只记日志不抛出）。"""
        raise NotImplementedError

    async def get_withdrawal_fee(self, network: str) -> Optional[float]:
        """
        查询 USDT 在指定网络的提现手续费（USDT 计价）。
        network 使用内部统一名：SOL / BSC / TRX / ETH 等。
        返回 None 表示查询失败或该网络不支持。
        """
        raise NotImplementedError

    async def withdraw(
        self,
        network: str,
        address: str,
        amount: float,
        *,
        memo: str = "",
    ) -> dict:
        """
        执行 USDT 提现。
        返回 {"success": bool, "id": str, "error": str}。
        network 使用内部统一名：SOL / BSC / TRX / ETH 等。
        """
        raise NotImplementedError


# ─── Binance ─────────────────────────────────────────────────────────────────

class BinanceClient(BaseClient):
    exchange = "binance"

    def _sign(self, params: dict) -> tuple[dict, dict]:
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(params)
        sig = hmac.new(self.keys["secret"].encode(), query.encode(), hashlib.sha256).hexdigest()
        params["signature"] = sig
        return params, {"X-MBX-APIKEY": self.keys["key"]}

    async def place_order(
        self, symbol: str, side: str, target_qty: float,
        ref_price: float, symbol_info=None,
    ) -> OrderResult:
        # Binance USDT-M：qty 直接是 base coin
        # 优先使用 symbol_info 提供的 step_size，如果不存在则根据价格猜测
        if symbol_info and symbol_info.qty_step > 0:
            step = symbol_info.qty_step
            # 根据 step 确定小数位
            if step >= 1.0:
                decimal_places = 0
            elif step >= 0.1:
                decimal_places = 1
            elif step >= 0.01:
                decimal_places = 2
            elif step >= 0.001:
                decimal_places = 3
            else:
                decimal_places = 6
        else:
            # 无规格数据时：根据价格动态选择精度
            if ref_price < 0.1:
                step, decimal_places = 1.0, 0
            elif ref_price < 1.0:
                step, decimal_places = 0.1, 1
            elif ref_price < 10.0:
                step, decimal_places = 0.01, 2
            elif ref_price < 100.0:
                step, decimal_places = 0.001, 3
            else:
                step, decimal_places = 0.0001, 4
        
        # 计算 qty：向上取整确保名义价值 >= 最小要求，然后按 step 取整
        qty = math.ceil(target_qty / step) * step
        if qty <= 0:
            return OrderResult(success=False, error=f"qty=0 (step={step}, target={target_qty})")
        
        # 强制格式化到指定精度，使用字符串避免浮点误差
        qty_str = f"{qty:.{decimal_places}f}"
        # 确保没有浮点误差产生的额外小数位
        qty = float(qty_str)

        params, headers = self._sign({
            "symbol": symbol.upper(), "side": side.upper(),
            "type": "MARKET", "quantity": qty_str,
        })
        try:
            sess = await self._sess()
            async with sess.post(
                f"{self.base}/fapi/v1/order",
                params=params, headers=headers, ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            if r.status == 200:
                fill     = float(data.get("avgPrice") or data.get("price") or ref_price)
                fill_qty = float(data.get("executedQty", qty))
                return OrderResult(
                    success=True, order_id=str(data.get("orderId", "")),
                    fill_price=fill, fill_size=fill_qty,
                    fee_usdt=fill_qty * fill * 0.0005,
                )
            return OrderResult(success=False, error=str(data))
        except Exception as e:
            return OrderResult(success=False, error=str(e))

    async def place_limit_order(
        self, symbol: str, side: str, target_qty: float,
        limit_price: float, symbol_info=None,
    ) -> OrderResult:
        step = symbol_info.qty_step if symbol_info and symbol_info.qty_step > 0 else 0.001
        qty  = max(step, math.floor(target_qty / step) * step)
        qty_str   = f"{qty:.{max(0, -int(math.floor(math.log10(step))))}f}" if step < 1 else f"{int(qty)}"
        price_str = f"{limit_price:.2f}"
        p, h = self._sign({
            "symbol": symbol.upper(), "side": side.upper(),
            "type": "LIMIT", "quantity": qty_str,
            "price": price_str, "timeInForce": "GTC",
        })
        try:
            sess = await self._sess()
            async with sess.post(
                f"{self.base}/fapi/v1/order",
                params=p, headers=h, ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            if r.status == 200:
                return OrderResult(
                    success=True, order_id=str(data.get("orderId", "")),
                    fill_price=limit_price, fill_size=qty,
                )
            return OrderResult(success=False, error=str(data))
        except Exception as e:
            return OrderResult(success=False, error=str(e))

    async def get_balance(self) -> float:
        p, h = self._sign({})
        sess = await self._sess()
        async with sess.get(
            f"{self.base}/fapi/v2/balance", params=p, headers=h,
            ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
        ) as r:
            data = await r.json()
        if isinstance(data, list):
            for item in data:
                if item.get("asset") == "USDT":
                    return float(item.get("availableBalance", 0))
        return 0.0

    async def get_positions(self, symbol: str = "") -> list[dict]:
        p = {"symbol": symbol.upper()} if symbol else {}
        p, h = self._sign(p)
        sess = await self._sess()
        async with sess.get(
            f"{self.base}/fapi/v2/positionRisk", params=p, headers=h,
            ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        if isinstance(data, list):
            return [x for x in data if float(x.get("positionAmt", 0)) != 0]
        return []

    async def get_open_orders(self, symbol: str = "") -> list[dict]:
        p = {"symbol": symbol.upper()} if symbol else {}
        p, h = self._sign(p)
        sess = await self._sess()
        async with sess.get(
            f"{self.base}/fapi/v1/openOrders", params=p, headers=h,
            ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        return data if isinstance(data, list) else []

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        p, h = self._sign({"symbol": symbol.upper(), "orderId": order_id})
        sess = await self._sess()
        async with sess.delete(
            f"{self.base}/fapi/v1/order", params=p, headers=h,
            ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        return r.status == 200

    async def transfer_to_spot(self, amount: float) -> bool:
        # Binance：期货 USDT → 现货 USDT（type=2），需通用划转权限。
        # 测试网期货/现货 API key 独立，此操作在测试网通常不可用。
        spot_base = "https://api.binance.com"  # 划转/提现始终走主网
        p, h = self._sign({"asset": "USDT", "amount": str(amount), "type": "2"})
        try:
            sess = await self._sess()
            async with sess.post(
                f"{spot_base}/sapi/v1/futures/transfer",
                params=p, headers=h, ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            return r.status == 200 and "tranId" in data
        except Exception:
            return False

    async def transfer_to_futures(self, amount: float) -> bool:
        # Binance：现货 USDT → USDT-M 期货（type=1）
        spot_base = "https://api.binance.com"
        p, h = self._sign({"asset": "USDT", "amount": str(amount), "type": "1"})
        try:
            sess = await self._sess()
            async with sess.post(
                f"{spot_base}/sapi/v1/futures/transfer",
                params=p, headers=h, ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            ok = r.status == 200 and "tranId" in data
            if not ok:
                logger.warning(f"[binance] transfer_to_futures 失败: status={r.status} resp={data}")
            return ok
        except Exception as e:
            logger.warning(f"[binance] transfer_to_futures 异常: {e}")
            return False

    async def get_spot_balance(self) -> float:
        # Binance 现货账户 USDT 余额
        spot_base = "https://api.binance.com"
        p, h = self._sign({})
        try:
            sess = await self._sess()
            async with sess.get(
                f"{spot_base}/sapi/v1/capital/config/getall",
                params=p, headers=h, ssl=False,
                timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if isinstance(data, list):
                for item in data:
                    if item.get("coin") == "USDT":
                        for net in (item.get("networkList") or []):
                            pass  # not needed here
                        return float(item.get("free", 0))
        except Exception:
            pass
        return 0.0

    async def get_earn_balance(self) -> float:
        # Binance Simple Earn 活期余额（只读）
        spot_base = "https://api.binance.com"
        try:
            sess = await self._sess()
            p, h = self._sign({"asset": "USDT", "size": "100"})
            async with sess.get(
                f"{spot_base}/sapi/v1/simple-earn/flexible/position",
                params=p, headers=h, ssl=False,
                timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json(content_type=None)
            if isinstance(data, dict) and "rows" in data:
                return sum(float(row.get("totalAmount", 0)) for row in (data.get("rows") or []) if row.get("asset") == "USDT")
        except Exception:
            pass
        return 0.0

    async def redeem_earn(self) -> float:
        # Binance Simple Earn 活期赎回 → 现货账户
        spot_base = "https://api.binance.com"
        total = 0.0
        try:
            sess = await self._sess()
            p, h = self._sign({"asset": "USDT", "size": "100"})
            async with sess.get(
                f"{spot_base}/sapi/v1/simple-earn/flexible/position",
                params=p, headers=h, ssl=False,
                timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json(content_type=None)
            for row in (data.get("rows") or [] if isinstance(data, dict) else []):
                if row.get("asset") != "USDT":
                    continue
                amt = float(row.get("totalAmount", 0))
                if amt < 0.01:
                    continue
                p2, h2 = self._sign({"productId": row["productId"], "redeemAll": "true"})
                async with sess.post(
                    f"{spot_base}/sapi/v1/simple-earn/flexible/redeem",
                    params=p2, headers=h2, ssl=False, **self._px(),
                ) as r2:
                    result = await r2.json(content_type=None)
                if result.get("success"):
                    total += amt
                else:
                    logger.warning(f"[binance] redeem_earn 失败: {result}")
        except Exception as e:
            logger.warning(f"[binance] redeem_earn 异常: {e}")
        return total

    async def get_total_balance(self) -> float:
        # Binance /fapi/v2/balance 同时返回 balance（总权益）和 availableBalance
        p, h = self._sign({})
        try:
            sess = await self._sess()
            async with sess.get(
                f"{self.base}/fapi/v2/balance", params=p, headers=h,
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if isinstance(data, list):
                for item in data:
                    if item.get("asset") == "USDT":
                        return float(item.get("balance", 0))
        except Exception as e:
            logger.debug(f"[binance] total_balance 查询失败: {e}")
        return 0.0

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        p, h = self._sign({"symbol": symbol.upper(), "leverage": leverage})
        try:
            sess = await self._sess()
            async with sess.post(
                f"{self.base}/fapi/v1/leverage",
                params=p, headers=h, ssl=False, **self._px(),
            ) as r:
                return r.status == 200
        except Exception as e:
            logger.debug(f"[binance] set_leverage 失败: {e}")
            return False

    async def get_withdrawal_fee(self, network: str) -> Optional[float]:
        from clients.withdrawal_addresses import get_api_network_name
        spot_base = "https://api.binance.com"
        p, h = self._sign({})
        try:
            sess = await self._sess()
            async with sess.get(
                f"{spot_base}/sapi/v1/capital/config/getall",
                params=p, headers=h, ssl=False,
                timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if isinstance(data, list):
                api_net = get_api_network_name("binance", network)
                for item in data:
                    if item.get("coin") == "USDT":
                        for net_info in (item.get("networkList") or []):
                            if net_info.get("network", "").upper() == api_net.upper():
                                if net_info.get("withdrawEnable"):
                                    return float(net_info.get("withdrawFee", 0))
        except Exception as e:
            logger.debug(f"[binance] 提现手续费查询失败: {e}")
        return None

    async def withdraw(self, network: str, address: str, amount: float, *, memo: str = "") -> dict:
        from clients.withdrawal_addresses import get_api_network_name
        spot_base = "https://api.binance.com"
        api_net = get_api_network_name("binance", network)
        body = {"coin": "USDT", "network": api_net, "address": address,
                "amount": str(amount)}
        if memo:
            body["addressTag"] = memo
        p, h = self._sign(body)
        try:
            sess = await self._sess()
            async with sess.post(
                f"{spot_base}/sapi/v1/capital/withdraw/apply",
                params=p, headers=h, ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            if r.status == 200 and "id" in data:
                return {"success": True, "id": str(data["id"]), "error": ""}
            return {"success": False, "id": "", "error": str(data)}
        except Exception as e:
            return {"success": False, "id": "", "error": str(e)}


# ─── OKX ─────────────────────────────────────────────────────────────────────

class OKXClient(BaseClient):
    exchange = "okx"

    def _sign(self, method: str, path: str, body: str = "") -> dict:
        ts  = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        sig = base64.b64encode(
            hmac.new(self.keys["secret"].encode(),
                     (ts + method.upper() + path + body).encode(),
                     hashlib.sha256).digest()
        ).decode()
        h = {
            "OK-ACCESS-KEY": self.keys["key"], "OK-ACCESS-SIGN": sig,
            "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": self.keys["passphrase"],
            "Content-Type": "application/json",
        }
        if not self.live:
            h["x-simulated-trading"] = "1"
        return h

    async def place_order(
        self, symbol: str, side: str, target_qty: float,
        ref_price: float, symbol_info=None, reduce_only: bool = False,
    ) -> OrderResult:
        # OKX：sz 单位为合约张数，1张 = ct_val base coins
        ct_val = symbol_info.native_ct_val if symbol_info else 0.01
        sz     = _to_contracts(target_qty, ct_val)
        if sz <= 0:
            return OrderResult(success=False, error="sz=0")

        path = "/api/v5/trade/order"

        async def _try(pos_side: str) -> dict:
            body_d = {"instId": symbol, "tdMode": "isolated",
                      "side": side.lower(), "posSide": pos_side,
                      "ordType": "market", "sz": str(sz)}
            body = json.dumps(body_d)
            sess = await self._sess()
            async with sess.post(
                f"{self.base}{path}", headers=self._sign("POST", path, body),
                data=body, ssl=False, **self._px(),
            ) as r:
                return await r.json()

        try:
            data = await _try("net")
            # 51000 = posSide 参数错误（账户处于双向持仓模式，需要 long/short）
            if data.get("code") == "1" and any(
                d.get("sCode") in ("51000",) and "posSide" in d.get("sMsg", "")
                for d in data.get("data", [])
            ):
                # 双向持仓模式：reduce_only=False(开仓) buy→long sell→short
                #               reduce_only=True(平仓)  sell→long buy→short
                if reduce_only:
                    hedge_side = "long" if side.lower() == "sell" else "short"
                else:
                    hedge_side = "long" if side.lower() == "buy" else "short"
                data = await _try(hedge_side)

            if data.get("code") == "0":
                order_id   = data["data"][0].get("ordId", "")
                fill_size  = sz * ct_val
                fill_price = await self._query_fill_price(symbol, order_id, ref_price)
                return OrderResult(
                    success=True, order_id=order_id,
                    fill_price=fill_price, fill_size=fill_size,
                    fee_usdt=fill_size * fill_price * 0.0005,
                )
            # 51010 = 当前账户模式不支持此操作，提供友好提示
            if data.get("code") == "1" and any(d.get("sCode") == "51010" for d in data.get("data", [])):
                return OrderResult(
                    success=False,
                    error="OKX Demo账户模式不支持合约交易。请在OKX网站或App上将账户模式从'简单模式'切换为'单币种保证金'、'跨币种保证金'或'组合保证金'模式 (交易页菜单 → 账户模式)。"
                )
            return OrderResult(success=False, error=str(data))
        except Exception as e:
            return OrderResult(success=False, error=str(e))

    async def _query_fill_price(self, inst_id: str, order_id: str, fallback: float) -> float:
        """查询 OKX 已成交订单的平均成交价，超时或失败时回退到 fallback。"""
        if not order_id:
            return fallback
        path = f"/api/v5/trade/order?instId={inst_id}&ordId={order_id}"
        try:
            sess = await self._sess()
            async with sess.get(
                f"{self.base}{path}", headers=self._sign("GET", path),
                ssl=False, timeout=aiohttp.ClientTimeout(total=2), **self._px(),
            ) as r:
                data = await r.json()
            if data.get("code") == "0" and data.get("data"):
                avg_px = float(data["data"][0].get("avgPx") or 0)
                if avg_px > 0:
                    return avg_px
        except Exception:
            pass
        return fallback

    async def place_limit_order(
        self, symbol: str, side: str, target_qty: float,
        limit_price: float, symbol_info=None, reduce_only: bool = False,
    ) -> OrderResult:
        ct_val = symbol_info.native_ct_val if symbol_info else 0.01
        sz = _to_contracts(target_qty, ct_val)
        if sz <= 0:
            return OrderResult(success=False, error="sz=0")

        path = "/api/v5/trade/order"

        async def _try(pos_side: str) -> dict:
            body_d = {"instId": symbol, "tdMode": "isolated",
                      "side": side.lower(), "posSide": pos_side,
                      "ordType": "limit", "sz": str(sz), "px": str(limit_price)}
            body = json.dumps(body_d)
            sess = await self._sess()
            async with sess.post(
                f"{self.base}{path}", headers=self._sign("POST", path, body),
                data=body, ssl=False, **self._px(),
            ) as r:
                return await r.json()

        try:
            data = await _try("net")
            if data.get("code") == "1" and any(
                d.get("sCode") in ("51000",) and "posSide" in d.get("sMsg", "")
                for d in data.get("data", [])
            ):
                if reduce_only:
                    hedge_side = "long" if side.lower() == "sell" else "short"
                else:
                    hedge_side = "long" if side.lower() == "buy" else "short"
                data = await _try(hedge_side)

            if data.get("code") == "0":
                return OrderResult(
                    success=True, order_id=data["data"][0].get("ordId", ""),
                    fill_price=limit_price, fill_size=sz * ct_val,
                )
            if data.get("code") == "1" and any(d.get("sCode") == "51010" for d in data.get("data", [])):
                return OrderResult(
                    success=False,
                    error="OKX Demo账户模式不支持合约交易。请在OKX网站或App上将账户模式从'简单模式'切换为'单币种保证金'、'跨币种保证金'或'组合保证金'模式 (交易页菜单 → 账户模式)。"
                )
            return OrderResult(success=False, error=str(data))
        except Exception as e:
            return OrderResult(success=False, error=str(e))

    async def get_balance(self) -> float:
        path = "/api/v5/account/balance?ccy=USDT"
        sess = await self._sess()
        async with sess.get(
            f"{self.base}{path}", headers=self._sign("GET", path),
            ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
        ) as r:
            data = await r.json()
        if data.get("code") == "0":
            for detail in (data.get("data") or [{}])[0].get("details", []):
                if detail.get("ccy") == "USDT":
                    return float(detail.get("availBal", 0))
        return 0.0

    async def get_positions(self, symbol: str = "") -> list[dict]:
        path = "/api/v5/account/positions?instType=SWAP"
        if symbol:
            path += f"&instId={symbol}"
        sess = await self._sess()
        async with sess.get(
            f"{self.base}{path}", headers=self._sign("GET", path),
            ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        if data.get("code") == "0":
            return [x for x in (data.get("data") or []) if float(x.get("pos", 0)) != 0]
        return []

    async def get_open_orders(self, symbol: str = "") -> list[dict]:
        path = "/api/v5/trade/orders-pending?instType=SWAP"
        if symbol:
            path += f"&instId={symbol}"
        sess = await self._sess()
        async with sess.get(
            f"{self.base}{path}", headers=self._sign("GET", path),
            ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        if data.get("code") == "0":
            return data.get("data") or []
        return []

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        body_d = {"instId": symbol, "ordId": order_id}
        body   = json.dumps(body_d)
        path   = "/api/v5/trade/cancel-order"
        sess = await self._sess()
        async with sess.post(
            f"{self.base}{path}", headers=self._sign("POST", path, body),
            data=body, ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        return data.get("code") == "0"

    async def transfer_to_spot(self, amount: float) -> bool:
        # OKX：交易账户（18）→ 资金账户（6）
        body_d = {"ccy": "USDT", "amt": str(amount), "from": "18", "to": "6",
                  "type": "0"}
        body = json.dumps(body_d)
        path = "/api/v5/asset/transfer"
        sess = await self._sess()
        async with sess.post(
            f"{self.base}{path}", headers=self._sign("POST", path, body),
            data=body, ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        return data.get("code") == "0"

    async def transfer_to_futures(self, amount: float) -> bool:
        # OKX：资金账户（6）→ 交易账户（18）
        body_d = {"ccy": "USDT", "amt": str(amount), "from": "6", "to": "18",
                  "type": "0"}
        body = json.dumps(body_d)
        path = "/api/v5/asset/transfer"
        sess = await self._sess()
        async with sess.post(
            f"{self.base}{path}", headers=self._sign("POST", path, body),
            data=body, ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        ok = data.get("code") == "0"
        if not ok:
            logger.warning(f"[okx] transfer_to_futures 失败: {data}")
        return ok

    async def get_spot_balance(self) -> float:
        # OKX 资金账户（funding account）USDT 余额
        path = "/api/v5/asset/balances?ccy=USDT"
        try:
            sess = await self._sess()
            async with sess.get(
                f"{self.base}{path}", headers=self._sign("GET", path),
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if data.get("code") == "0":
                for item in (data.get("data") or []):
                    if item.get("ccy") == "USDT":
                        return float(item.get("availBal", 0))
        except Exception as e:
            logger.debug(f"[okx] spot balance 查询失败: {e}")
        return 0.0

    async def get_earn_balance(self) -> float:
        # OKX 活期理财余额（只读）
        try:
            sess = await self._sess()
            path = "/api/v5/finance/savings/balance?ccy=USDT"
            async with sess.get(
                f"{self.base}{path}", headers=self._sign("GET", path),
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if data.get("code") == "0":
                return sum(float(i.get("amt", 0)) for i in (data.get("data") or []) if i.get("ccy") == "USDT")
        except Exception:
            pass
        return 0.0

    async def redeem_earn(self) -> float:
        # OKX 活期理财赎回 → 资金账户
        total = 0.0
        try:
            sess = await self._sess()
            path = "/api/v5/finance/savings/balance?ccy=USDT"
            async with sess.get(
                f"{self.base}{path}", headers=self._sign("GET", path),
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            for item in (data.get("data") or [] if data.get("code") == "0" else []):
                if item.get("ccy") != "USDT":
                    continue
                amt_str = item.get("amt", "0")
                amt = float(amt_str)
                if amt < 0.01:
                    continue
                body_d = {"ccy": "USDT", "amt": amt_str, "side": "redempt"}
                body = json.dumps(body_d)
                rpath = "/api/v5/finance/savings/purchase-redempt"
                async with sess.post(
                    f"{self.base}{rpath}", headers=self._sign("POST", rpath, body),
                    data=body, ssl=False, **self._px(),
                ) as r2:
                    result = await r2.json()
                if result.get("code") == "0":
                    total += amt
                else:
                    logger.warning(f"[okx] redeem_earn 失败: {result}")
        except Exception as e:
            logger.warning(f"[okx] redeem_earn 异常: {e}")
        return total

    async def get_total_balance(self) -> float:
        # OKX /api/v5/account/balance details[USDT].eq = 总权益（含冻结+未实现盈亏）
        path = "/api/v5/account/balance?ccy=USDT"
        try:
            sess = await self._sess()
            async with sess.get(
                f"{self.base}{path}", headers=self._sign("GET", path),
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if data.get("code") == "0":
                for detail in (data.get("data") or [{}])[0].get("details", []):
                    if detail.get("ccy") == "USDT":
                        return float(detail.get("eq", 0))
        except Exception as e:
            logger.debug(f"[okx] total_balance 查询失败: {e}")
        return 0.0

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        # OKX isolated 模式：per-instrument 设置杠杆；可在开仓前调用
        body_d = {"instId": symbol, "lever": str(leverage), "mgnMode": "isolated"}
        body   = json.dumps(body_d)
        path   = "/api/v5/account/set-leverage"
        try:
            sess = await self._sess()
            async with sess.post(
                f"{self.base}{path}", headers=self._sign("POST", path, body),
                data=body, ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            return data.get("code") == "0"
        except Exception as e:
            logger.debug(f"[okx] set_leverage 失败: {e}")
            return False

    async def get_withdrawal_fee(self, network: str) -> Optional[float]:
        from clients.withdrawal_addresses import get_api_network_name
        path = "/api/v5/asset/currencies?ccy=USDT"
        api_net = get_api_network_name("okx", network)

        def _chain_matches(chain: str, want: str) -> bool:
            if not chain or not want:
                return False
            cu, wu = chain.upper(), want.upper()
            tail = chain.split("-", 1)[-1].strip().upper()
            if tail == wu:
                return True
            if wu in cu:
                return True
            # OKX 部分链全名较长，内部码需宽松匹配
            if wu == "BSC" and ("BEP20" in cu or "BSC" in cu):
                return True
            if wu == "AVAX" and "AVAX" in cu:
                return True
            return False

        try:
            sess = await self._sess()
            async with sess.get(
                f"{self.base}{path}", headers=self._sign("GET", path),
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if data.get("code") == "0":
                for item in (data.get("data") or []):
                    if item.get("ccy") != "USDT":
                        continue
                    chain = item.get("chain") or ""
                    if not _chain_matches(chain, api_net):
                        continue
                    if not item.get("canWd"):
                        continue
                    raw = item.get("minFee")
                    if raw is None or raw == "":
                        continue
                    return float(raw)
        except Exception as e:
            logger.debug(f"[okx] 提现手续费查询失败: {e}")
        return None

    async def withdraw(self, network: str, address: str, amount: float, *, memo: str = "") -> dict:
        from clients.withdrawal_addresses import get_api_network_name
        api_net = get_api_network_name("okx", network)
        # OKX chain 格式：USDT-Solana / USDT-BSC / USDT-TRC20 等
        chain = f"USDT-{api_net}"
        body_d = {"ccy": "USDT", "amt": str(amount), "dest": "4",
                  "toAddr": address, "chain": chain}
        if memo:
            body_d["toAddr"] = f"{address}:{memo}"
        body = json.dumps(body_d)
        path = "/api/v5/asset/withdrawal"
        try:
            sess = await self._sess()
            async with sess.post(
                f"{self.base}{path}", headers=self._sign("POST", path, body),
                data=body, ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            if data.get("code") == "0":
                wd_id = (data.get("data") or [{}])[0].get("wdId", "")
                return {"success": True, "id": str(wd_id), "error": ""}
            return {"success": False, "id": "", "error": str(data)}
        except Exception as e:
            return {"success": False, "id": "", "error": str(e)}


# ─── Gate ─────────────────────────────────────────────────────────────────────

class GateClient(BaseClient):
    exchange = "gate"

    def _sign(self, method: str, path: str, body: str = "", query: str = "") -> dict:
        # Gate v4：GET 带 query 时签名字符串第三段为 query_string（见官方 gen_sign）
        ts        = str(int(time.time()))
        body_hash = hashlib.sha512(body.encode() if body else b"").hexdigest()
        msg       = f"{method.upper()}\n{path}\n{query}\n{body_hash}\n{ts}"
        sig       = hmac.new(self.keys["secret"].encode(), msg.encode(), hashlib.sha512).hexdigest()
        return {"KEY": self.keys["key"], "SIGN": sig,
                "Timestamp": ts, "Content-Type": "application/json"}

    async def place_order(
        self, symbol: str, side: str, target_qty: float,
        ref_price: float, symbol_info=None, reduce_only: bool = False,
    ) -> OrderResult:
        # Gate 线性永续：size 单位为合约张数，1张 = ct_val(quanto_multiplier) base coins
        ct_val = symbol_info.native_ct_val if symbol_info and symbol_info.native_ct_val > 0 else (
            1.0 / ref_price if ref_price > 0 else 0.0001  # 1 USD per contract fallback
        )
        sz = _to_contracts(target_qty, ct_val)
        if sz <= 0:
            return OrderResult(success=False, error="sz=0")
        if side == "sell":
            sz = -sz   # Gate 用负数表示做空

        body_d = {"contract": symbol, "size": sz, "price": "0", "tif": "ioc"}
        if reduce_only:
            body_d["reduce_only"] = True
        body   = json.dumps(body_d)
        path   = "/api/v4/futures/usdt/orders"
        try:
            sess = await self._sess()
            async with sess.post(
                f"{self.base}{path}", headers=self._sign("POST", path, body),
                data=body, ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            if r.status in (200, 201):
                fill      = float(data.get("fill_price") or data.get("price") or ref_price)
                fill_size = abs(sz) * ct_val
                return OrderResult(
                    success=True, order_id=str(data.get("id", "")),
                    fill_price=fill, fill_size=fill_size,
                    fee_usdt=fill_size * fill * 0.00075,
                )
            return OrderResult(success=False, error=str(data))
        except Exception as e:
            return OrderResult(success=False, error=str(e))

    async def place_limit_order(
        self, symbol: str, side: str, target_qty: float,
        limit_price: float, symbol_info=None,
    ) -> OrderResult:
        ct_val = symbol_info.native_ct_val if symbol_info and symbol_info.native_ct_val > 0 else (
            1.0 / limit_price if limit_price > 0 else 0.001
        )
        sz = _to_contracts(target_qty, ct_val)
        if sz <= 0:
            return OrderResult(success=False, error="sz=0")
        if side == "sell":
            sz = -sz
        body_d = {"contract": symbol, "size": sz,
                  "price": str(limit_price), "tif": "gtc"}
        body = json.dumps(body_d)
        path = "/api/v4/futures/usdt/orders"
        try:
            sess = await self._sess()
            async with sess.post(
                f"{self.base}{path}", headers=self._sign("POST", path, body),
                data=body, ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            if r.status in (200, 201):
                return OrderResult(
                    success=True, order_id=str(data.get("id", "")),
                    fill_price=limit_price, fill_size=abs(sz) * ct_val,
                )
            return OrderResult(success=False, error=str(data))
        except Exception as e:
            return OrderResult(success=False, error=str(e))

    async def get_balance(self) -> float:
        path = "/api/v4/futures/usdt/accounts"
        sess = await self._sess()
        async with sess.get(
            f"{self.base}{path}", headers=self._sign("GET", path),
            ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
        ) as r:
            data = await r.json()
        if isinstance(data, dict):
            return float(data.get("available", 0))
        return 0.0

    async def get_positions(self, symbol: str = "") -> list[dict]:
        path = f"/api/v4/futures/usdt/positions/{symbol}" if symbol else "/api/v4/futures/usdt/positions"
        sess = await self._sess()
        async with sess.get(
            f"{self.base}{path}", headers=self._sign("GET", path),
            ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        if isinstance(data, list):
            return [x for x in data if float(x.get("size", 0)) != 0]
        if isinstance(data, dict) and float(data.get("size", 0)) != 0:
            return [data]
        return []

    async def get_open_orders(self, symbol: str = "") -> list[dict]:
        path = "/api/v4/futures/usdt/orders?status=open"
        if symbol:
            path += f"&contract={symbol}"
        sess = await self._sess()
        async with sess.get(
            f"{self.base}{path}", headers=self._sign("GET", path),
            ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        return data if isinstance(data, list) else []

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        path = f"/api/v4/futures/usdt/orders/{order_id}"
        sess = await self._sess()
        async with sess.delete(
            f"{self.base}{path}", headers=self._sign("DELETE", path),
            ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        return r.status == 200

    async def transfer_to_spot(self, amount: float) -> bool:
        # Gate.io：期货 USDT → 现货 USDT
        body_d = {"currency": "USDT", "amount": str(amount),
                  "from": "futures", "to": "spot"}
        body = json.dumps(body_d)
        path = "/api/v4/wallet/transfers"
        sess = await self._sess()
        async with sess.post(
            f"{self.base}{path}", headers=self._sign("POST", path, body),
            data=body, ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        return r.status in (200, 201)

    async def transfer_to_futures(self, amount: float) -> bool:
        # Gate.io：现货 USDT → USDT 期货（settle=usdt 必填）
        body_d = {"currency": "USDT", "amount": str(amount),
                  "from": "spot", "to": "futures", "settle": "usdt"}
        body = json.dumps(body_d)
        path = "/api/v4/wallet/transfers"
        sess = await self._sess()
        async with sess.post(
            f"{self.base}{path}", headers=self._sign("POST", path, body),
            data=body, ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        ok = r.status in (200, 201)
        if not ok:
            logger.warning(f"[gate] transfer_to_futures 失败: status={r.status} resp={data}")
        return ok

    async def get_spot_balance(self) -> float:
        # Gate 现货账户 USDT 余额
        path = "/api/v4/spot/accounts"
        try:
            sess = await self._sess()
            async with sess.get(
                f"{self.base}{path}", headers=self._sign("GET", path),
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if isinstance(data, list):
                for item in data:
                    if item.get("currency") == "USDT":
                        return float(item.get("available", 0))
        except Exception as e:
            logger.debug(f"[gate] spot balance 查询失败: {e}")
        return 0.0

    async def get_total_balance(self) -> float:
        # Gate /api/v4/futures/usdt/accounts 的 total 字段 = 总权益
        path = "/api/v4/futures/usdt/accounts"
        try:
            sess = await self._sess()
            async with sess.get(
                f"{self.base}{path}", headers=self._sign("GET", path),
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if isinstance(data, dict):
                return float(data.get("total", 0))
        except Exception as e:
            logger.debug(f"[gate] total_balance 查询失败: {e}")
        return 0.0

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        # Gate：通过 POST /positions/{contract}/leverage 设置杠杆
        # 若该 symbol 尚无持仓，API 会报错（正常情况，忽略即可）
        path  = f"/api/v4/futures/usdt/positions/{symbol}/leverage"
        query = f"leverage={leverage}"
        try:
            sess = await self._sess()
            async with sess.post(
                f"{self.base}{path}?{query}",
                headers=self._sign("POST", path, "", query),
                ssl=False, **self._px(),
            ) as r:
                return r.status in (200, 201)
        except Exception as e:
            logger.debug(f"[gate] set_leverage 失败: {e}")
            return False

    async def get_withdrawal_fee(self, network: str) -> Optional[float]:
        from clients.withdrawal_addresses import get_api_network_name
        api_net = get_api_network_name("gate", network)
        # 官方：GET /api/v4/wallet/withdraw_status（不是 /withdraw/status）
        path = "/api/v4/wallet/withdraw_status"
        query = "currency=USDT"

        # withdraw_fix_on_chains 的键常见为链代号；与提币参数 chain 可能为 ETH 或 ERC20 等，多别名尝试
        _GATE_FEE_ALIASES: dict[str, tuple[str, ...]] = {
            "ETH": ("ETH", "ERC20"),
            "TRX": ("TRX", "TRC20"),
            "BSC": ("BSC", "BEP20", "BNB"),
            "SOL": ("SOL",),
            "ARB": ("ARB", "ARBITRUM", "ARBEVM"),
            "AVAX": ("AVAX", "AVAX_C", "AVAXC"),
            "OP": ("OP", "OPTIMISM", "OPETH"),
        }

        def _fee_from_fix_map(fix_map: dict, want: str) -> Optional[float]:
            if not fix_map or not want:
                return None
            candidates = [want.upper()]
            for a in _GATE_FEE_ALIASES.get(want.upper(), ()):
                if a.upper() not in candidates:
                    candidates.append(a.upper())
            for wu in candidates:
                for k, v in fix_map.items():
                    if str(k).upper() == wu:
                        try:
                            return float(v)
                        except (TypeError, ValueError):
                            return None
            return None

        try:
            sess = await self._sess()
            url = f"{self.base}{path}?{query}"
            async with sess.get(
                url, headers=self._sign("GET", path, "", query),
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if isinstance(data, list):
                for item in data:
                    if item.get("currency") != "USDT":
                        continue
                    # 官方文档：手续费在 withdraw_fix_on_chains（按链名的字典），不是 chains 数组
                    fee = _fee_from_fix_map(item.get("withdraw_fix_on_chains") or {}, api_net)
                    if fee is not None:
                        return fee
                    # 兼容旧版/部分环境返回的 chains 列表
                    for chain in item.get("chains") or []:
                        if str(chain.get("chain", "")).upper() == api_net.upper():
                            if chain.get("is_withdraw_disabled") == 0:
                                raw = chain.get("withdraw_fix_on_chains")
                                if isinstance(raw, dict):
                                    f2 = _fee_from_fix_map(raw, api_net)
                                    if f2 is not None:
                                        return f2
                                raw2 = chain.get("withdraw_fee") or chain.get("withdrawFix")
                                if raw2 is not None and raw2 != "":
                                    try:
                                        return float(raw2)
                                    except (TypeError, ValueError):
                                        pass
        except Exception as e:
            logger.debug(f"[gate] 提现手续费查询失败: {e}")
        return None

    async def withdraw(self, network: str, address: str, amount: float, *, memo: str = "") -> dict:
        from clients.withdrawal_addresses import get_api_network_name
        api_net = get_api_network_name("gate", network)
        body_d = {"currency": "USDT", "address": address,
                  "amount": str(amount), "chain": api_net}
        if memo:
            body_d["memo"] = memo
        body = json.dumps(body_d)
        path = "/api/v4/withdrawals"
        try:
            sess = await self._sess()
            async with sess.post(
                f"{self.base}{path}", headers=self._sign("POST", path, body),
                data=body, ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            if r.status in (200, 201) and "id" in data:
                return {"success": True, "id": str(data["id"]), "error": ""}
            return {"success": False, "id": "", "error": str(data)}
        except Exception as e:
            return {"success": False, "id": "", "error": str(e)}


# ─── Bitget ───────────────────────────────────────────────────────────────────

class BitgetClient(BaseClient):
    exchange = "bitget"

    def _sign(self, method: str, path: str, body: str = "", use_pap: bool = True) -> dict:
        ts  = str(int(time.time() * 1000))
        sig = base64.b64encode(
            hmac.new(self.keys["secret"].encode(),
                     (ts + method.upper() + path + body).encode(),
                     hashlib.sha256).digest()
        ).decode()
        h = {"ACCESS-KEY": self.keys["key"], "ACCESS-SIGN": sig,
             "ACCESS-TIMESTAMP": ts, "ACCESS-PASSPHRASE": self.keys["passphrase"],
             "Content-Type": "application/json"}
        # 只有 PAP Trading 模式且非实盘才添加 paptrading header
        if not self.live and use_pap:
            h["paptrading"] = "1"
        return h

    async def place_order(
        self, symbol: str, side: str, target_qty: float,
        ref_price: float, symbol_info=None,
    ) -> OrderResult:
        # Bitget：size 单位直接是 base coin（native_ct_val=1.0）
        step = symbol_info.qty_step if symbol_info and symbol_info.qty_step > 0 else 0.001
        qty  = math.floor(target_qty / step) * step
        qty  = round(max(qty, step), 8)
        if qty <= 0:
            return OrderResult(success=False, error="qty=0")

        # Bitget 有两种 Demo 模式，都尝试
        # 1. PAP Trading: productType=USDT-FUTURES, marginCoin=USDT, 有 paptrading header (优先)
        # 2. 模拟币模式: productType=SUSDT-FUTURES, marginCoin=SUSDT, 无 paptrading header
        for product_type, use_pap, margin_coin in [
            ("USDT-FUTURES", True, "USDT"),     # PAP模式优先（标准合约如 BTCUSDT）
            ("SUSDT-FUTURES", False, "SUSDT"),  # 模拟币模式（模拟合约如 SBTCUSDT）
        ]:
            body_d = {
                "symbol": symbol, "productType": product_type,
                "marginMode": "isolated", "marginCoin": margin_coin,
                "size": str(qty), "side": side.lower(),
                "tradeSide": "open", "orderType": "market",
            }
            body = json.dumps(body_d)
            path = "/api/v2/mix/order/place-order"
            try:
                sess = await self._sess()
                headers = self._sign("POST", path, body, use_pap=use_pap)
                logger.info(f"[bitget] 下单请求: {body_d}")
                async with sess.post(
                    f"{self.base}{path}", headers=headers,
                    data=body, ssl=False, **self._px(),
                ) as r:
                    data = await r.json()
                logger.info(f"[bitget] 下单响应 ({product_type}): {data}")
                if str(data.get("code", "")) == "00000":
                    order_id   = str(data.get("data", {}).get("orderId", ""))
                    fill_price = await self._query_fill_price(symbol, order_id, ref_price, product_type, use_pap)
                    return OrderResult(
                        success=True, order_id=order_id,
                        fill_price=fill_price, fill_size=qty,
                        fee_usdt=qty * fill_price * 0.0006,
                    )
                # 40099 = 环境错误（API Key 类型与模式不匹配），尝试另一种模式
                if data.get("code") == "40099":
                    continue
                # 40778 = 合约不支持 SUSDT 保证金（模拟币模式使用了标准合约代码）
                if data.get("code") == "40778" and "SUSDT" in str(data.get("msg", "")):
                    return OrderResult(
                        success=False,
                        error=f"Bitget Demo 模式不匹配：当前为模拟币模式(SUSDT-FUTURES)，但使用了标准合约'{symbol}'。"
                               f"请使用模拟币合约(如SBTCSUSDT)或创建PAP Trading类型的Demo API Key。"
                    )
                return OrderResult(success=False, error=str(data))
            except Exception as e:
                return OrderResult(success=False, error=str(e))
        return OrderResult(success=False, error="Bitget 两种模式都失败")

    async def _query_fill_price(self, symbol: str, order_id: str, fallback: float,
                                  product_type: str = "USDT-FUTURES", use_pap: bool = True) -> float:
        """查询 Bitget 已成交订单的平均成交价，超时或失败时回退到 fallback。"""
        if not order_id:
            return fallback
        path = f"/api/v2/mix/order/detail?symbol={symbol}&productType={product_type}&orderId={order_id}"
        try:
            ts  = str(int(time.time() * 1000))
            sig = base64.b64encode(
                hmac.new(self.keys["secret"].encode(),
                         (ts + "GET" + path).encode(),
                         hashlib.sha256).digest()
            ).decode()
            headers = {"ACCESS-KEY": self.keys["key"], "ACCESS-SIGN": sig,
                       "ACCESS-TIMESTAMP": ts, "ACCESS-PASSPHRASE": self.keys["passphrase"]}
            if not self.live and use_pap:
                headers["paptrading"] = "1"
            sess = await self._sess()
            async with sess.get(
                f"{self.base}{path}", headers=headers, ssl=False,
                timeout=aiohttp.ClientTimeout(total=2), **self._px(),
            ) as r:
                data = await r.json()
            if str(data.get("code", "")) == "00000" and data.get("data"):
                avg_px = float(data["data"].get("priceAvg") or 0)
                if avg_px > 0:
                    return avg_px
        except Exception:
            pass
        return fallback

    async def place_limit_order(
        self, symbol: str, side: str, target_qty: float,
        limit_price: float, symbol_info=None,
    ) -> OrderResult:
        step = symbol_info.qty_step if symbol_info and symbol_info.qty_step > 0 else 0.001
        qty  = round(max(step, math.floor(target_qty / step) * step), 8)
        if qty <= 0:
            return OrderResult(success=False, error="qty=0")
        for product_type, use_pap, margin_coin in [
            ("USDT-FUTURES",  True,  "USDT"),  # PAP模式优先
            ("SUSDT-FUTURES", False, "SUSDT"),
        ]:
            body_d = {
                "symbol": symbol, "productType": product_type,
                "marginMode": "isolated", "marginCoin": margin_coin,
                "size": str(qty), "side": side.lower(),
                "tradeSide": "open", "orderType": "limit",
                "price": str(limit_price),
            }
            body = json.dumps(body_d)
            path = "/api/v2/mix/order/place-order"
            try:
                sess = await self._sess()
                async with sess.post(
                    f"{self.base}{path}",
                    headers=self._sign("POST", path, body, use_pap=use_pap),
                    data=body, ssl=False, **self._px(),
                ) as r:
                    data = await r.json()
                if str(data.get("code", "")) == "00000":
                    return OrderResult(
                        success=True,
                        order_id=str(data.get("data", {}).get("orderId", "")),
                        fill_price=limit_price, fill_size=qty,
                    )
                if data.get("code") == "40099":
                    continue
                if data.get("code") == "40778" and "SUSDT" in str(data.get("msg", "")):
                    return OrderResult(
                        success=False,
                        error=f"Bitget Demo 模式不匹配：当前为模拟币模式(SUSDT-FUTURES)，但使用了标准合约'{symbol}'。"
                               f"请使用模拟币合约(如SBTCSUSDT)或创建PAP Trading类型的Demo API Key。"
                    )
                return OrderResult(success=False, error=str(data))
            except Exception as e:
                return OrderResult(success=False, error=str(e))
        return OrderResult(success=False, error="Bitget 两种模式都失败")

    async def get_balance(self) -> float:
        for product_type, use_pap in [("USDT-FUTURES", True), ("SUSDT-FUTURES", False)]:
            path = f"/api/v2/mix/account/accounts?productType={product_type}"
            ts   = str(int(time.time() * 1000))
            sig  = base64.b64encode(
                hmac.new(self.keys["secret"].encode(),
                         (ts + "GET" + path).encode(), hashlib.sha256).digest()
            ).decode()
            headers = {
                "ACCESS-KEY": self.keys["key"], "ACCESS-SIGN": sig,
                "ACCESS-TIMESTAMP": ts,
                "ACCESS-PASSPHRASE": self.keys.get("passphrase", ""),
            }
            if not self.live and use_pap:
                headers["paptrading"] = "1"
            try:
                sess = await self._sess()
                async with sess.get(
                    f"{self.base}{path}", headers=headers, ssl=False,
                    timeout=aiohttp.ClientTimeout(total=5), **self._px(),
                ) as r:
                    data = await r.json()
                if str(data.get("code", "")) == "00000":
                    for item in (data.get("data") or []):
                        if item.get("marginCoin") in ["USDT", "SUSDT"]:
                            return float(item.get("available", 0))
            except Exception:
                continue
        return 0.0

    async def get_positions(self, symbol: str = "") -> list[dict]:
        for product_type, use_pap in [("USDT-FUTURES", True), ("SUSDT-FUTURES", False)]:
            path = f"/api/v2/mix/position/all-position?productType={product_type}"
            if symbol:
                path += f"&symbol={symbol}"
            sess = await self._sess()
            async with sess.get(
                f"{self.base}{path}",
                headers=self._sign("GET", path, use_pap=use_pap),
                ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            if str(data.get("code", "")) == "00000":
                return [x for x in (data.get("data") or []) if float(x.get("total", 0)) != 0]
        return []

    async def get_open_orders(self, symbol: str = "") -> list[dict]:
        for product_type, use_pap in [("USDT-FUTURES", True), ("SUSDT-FUTURES", False)]:
            path = f"/api/v2/mix/order/orders-pending?productType={product_type}"
            if symbol:
                path += f"&symbol={symbol}"
            sess = await self._sess()
            async with sess.get(
                f"{self.base}{path}",
                headers=self._sign("GET", path, body="", use_pap=use_pap),
                ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            if str(data.get("code", "")) == "00000":
                result = data.get("data")
                # Bitget API 返回嵌套结构: {'entrustedList': [...], 'endId': ...}
                if isinstance(result, dict) and "entrustedList" in result:
                    return result.get("entrustedList") or []
                elif isinstance(result, list):
                    return result
                elif isinstance(result, dict):
                    return [result]
                else:
                    return []
        return []

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        for product_type, use_pap in [("USDT-FUTURES", True), ("SUSDT-FUTURES", False)]:
            body_d = {"symbol": symbol, "productType": product_type, "orderId": order_id}
            body   = json.dumps(body_d)
            path   = "/api/v2/mix/order/cancel-order"
            try:
                sess = await self._sess()
                async with sess.post(
                    f"{self.base}{path}",
                    headers=self._sign("POST", path, body, use_pap=use_pap),
                    data=body, ssl=False, **self._px(),
                ) as r:
                    data = await r.json()
                if str(data.get("code", "")) == "00000":
                    return True
                if data.get("code") == "40099":
                    continue
            except Exception:
                continue
        return False

    async def transfer_to_spot(self, amount: float) -> bool:
        # Bitget：期货账户 → 现货账户
        body_d = {
            "fromType": "usdt_futures", "toType": "spot",
            "amount": str(amount), "coin": "USDT",
        }
        body = json.dumps(body_d)
        path = "/api/v2/spot/wallet/transfer"
        sess = await self._sess()
        async with sess.post(
            f"{self.base}{path}",
            headers=self._sign("POST", path, body, use_pap=False),
            data=body, ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        return str(data.get("code", "")) == "00000"

    async def transfer_to_futures(self, amount: float) -> bool:
        # Bitget：现货账户 → 期货账户
        body_d = {
            "fromType": "spot", "toType": "usdt_futures",
            "amount": str(amount), "coin": "USDT",
        }
        body = json.dumps(body_d)
        path = "/api/v2/spot/wallet/transfer"
        sess = await self._sess()
        async with sess.post(
            f"{self.base}{path}",
            headers=self._sign("POST", path, body, use_pap=False),
            data=body, ssl=False, **self._px(),
        ) as r:
            data = await r.json()
        ok = str(data.get("code", "")) == "00000"
        if not ok:
            logger.warning(f"[bitget] transfer_to_futures 失败: {data}")
        return ok

    async def get_spot_balance(self) -> float:
        # Bitget 现货账户 USDT 余额
        path = "/api/v2/spot/account/assets?coin=USDT"
        try:
            sess = await self._sess()
            async with sess.get(
                f"{self.base}{path}",
                headers=self._sign("GET", path, use_pap=False),
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if str(data.get("code", "")) == "00000":
                for item in (data.get("data") or []):
                    if item.get("coin") == "USDT":
                        return float(item.get("available", 0))
        except Exception as e:
            logger.debug(f"[bitget] spot balance 查询失败: {e}")
        return 0.0

    async def get_earn_balance(self) -> float:
        # Bitget 活期理财余额（只读）
        try:
            sess = await self._sess()
            path = "/api/v2/earn/savings/assets?coin=USDT"
            async with sess.get(
                f"{self.base}{path}",
                headers=self._sign("GET", path, use_pap=False),
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if str(data.get("code", "")) == "00000":
                raw = data.get("data") or {}
                items = raw.get("resultList") or [] if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
                return sum(float(i.get("holdAmount", 0)) for i in items)
        except Exception:
            pass
        return 0.0

    async def redeem_earn(self) -> float:
        # Bitget 活期理财赎回 → 现货账户
        total = 0.0
        try:
            sess = await self._sess()
            path = "/api/v2/earn/savings/assets?coin=USDT"
            async with sess.get(
                f"{self.base}{path}",
                headers=self._sign("GET", path, use_pap=False),
                ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if str(data.get("code", "")) == "00000":
                raw = data.get("data") or {}
                items = raw.get("resultList") or [] if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
                for item in items:
                    amt = float(item.get("holdAmount", 0))
                    if amt < 0.01:
                        continue
                    order_id = item.get("orderId", "")
                    period_type = item.get("periodType", "flexible")
                    body_d = {"orderId": order_id, "periodType": period_type}
                    body = json.dumps(body_d)
                    rpath = "/api/v2/earn/savings/redeem"
                    async with sess.post(
                        f"{self.base}{rpath}",
                        headers=self._sign("POST", rpath, body, use_pap=False),
                        data=body, ssl=False, **self._px(),
                    ) as r2:
                        result = await r2.json()
                    if str(result.get("code", "")) == "00000":
                        total += amt
                    else:
                        logger.warning(f"[bitget] redeem_earn 失败: {result}")
        except Exception as e:
            logger.warning(f"[bitget] redeem_earn 异常: {e}")
        return total

    async def get_total_balance(self) -> float:
        # Bitget: available + locked（持仓保证金）≈ 总权益（保守估算，未含未实现盈亏）
        for product_type, use_pap in [("USDT-FUTURES", True), ("SUSDT-FUTURES", False)]:
            path = f"/api/v2/mix/account/accounts?productType={product_type}"
            try:
                sess = await self._sess()
                async with sess.get(
                    f"{self.base}{path}",
                    headers=self._sign("GET", path, use_pap=use_pap),
                    ssl=False, timeout=aiohttp.ClientTimeout(total=5), **self._px(),
                ) as r:
                    data = await r.json()
                if str(data.get("code", "")) == "00000":
                    for item in (data.get("data") or []):
                        if item.get("marginCoin") in ["USDT", "SUSDT"]:
                            avail  = float(item.get("available", 0))
                            locked = float(item.get("locked", 0))
                            return avail + locked
            except Exception as e:
                logger.debug(f"[bitget] total_balance 查询失败: {e}")
                continue
        return 0.0

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        body_d = {
            "symbol": symbol, "productType": "USDT-FUTURES",
            "marginCoin": "USDT", "leverage": str(leverage),
        }
        body = json.dumps(body_d)
        path = "/api/v2/mix/account/set-leverage"
        try:
            sess = await self._sess()
            async with sess.post(
                f"{self.base}{path}",
                headers=self._sign("POST", path, body, use_pap=False),
                data=body, ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            return str(data.get("code", "")) == "00000"
        except Exception as e:
            logger.debug(f"[bitget] set_leverage 失败: {e}")
            return False

    async def get_withdrawal_fee(self, network: str) -> Optional[float]:
        from clients.withdrawal_addresses import get_api_network_name
        # Bitget 公开接口，无需签名
        api_net = get_api_network_name("bitget", network)
        # 官方：GET /api/v2/spot/public/coins（/api/v2/public/coins 无效）
        path = "/api/v2/spot/public/coins?coin=USDT"
        try:
            sess = await self._sess()
            async with sess.get(
                f"{self.base}{path}", ssl=False,
                timeout=aiohttp.ClientTimeout(total=5), **self._px(),
            ) as r:
                data = await r.json()
            if str(data.get("code", "")) == "00000":
                for item in (data.get("data") or []):
                    if item.get("coin") == "USDT":
                        for chain in (item.get("chains") or []):
                            if str(chain.get("chain", "")).upper() != api_net.upper():
                                continue
                            w = chain.get("withdrawable")
                            if w not in (True, "true", "True", 1, "1", "yes"):
                                continue
                            raw = chain.get("withdrawFee") or chain.get("withdraw_fee") or "0"
                            try:
                                return float(raw)
                            except (TypeError, ValueError):
                                return None
        except Exception as e:
            logger.debug(f"[bitget] 提现手续费查询失败: {e}")
        return None

    async def withdraw(self, network: str, address: str, amount: float, *, memo: str = "") -> dict:
        from clients.withdrawal_addresses import get_api_network_name
        api_net = get_api_network_name("bitget", network)
        body_d = {"coin": "USDT", "address": address,
                  "chain": api_net, "size": str(amount), "transferType": "on_chain"}
        if memo:
            body_d["tag"] = memo
        body = json.dumps(body_d)
        path = "/api/v2/spot/wallet/withdrawal"
        try:
            sess = await self._sess()
            async with sess.post(
                f"{self.base}{path}",
                headers=self._sign("POST", path, body, use_pap=False),
                data=body, ssl=False, **self._px(),
            ) as r:
                data = await r.json()
            if str(data.get("code", "")) == "00000":
                wd_id = str((data.get("data") or {}).get("orderId", ""))
                return {"success": True, "id": wd_id, "error": ""}
            return {"success": False, "id": "", "error": str(data)}
        except Exception as e:
            return {"success": False, "id": "", "error": str(e)}


# ─── 工厂函数 ─────────────────────────────────────────────────────────────────

def build_clients(live: bool, proxy: str = "") -> dict[str, BaseClient]:
    """
    构建交易所客户端实例。
    
    Args:
        live: True=使用实盘 API，False=使用模拟盘/测试网 API
        proxy: HTTP 代理，默认空（直连）
    
    Returns:
        dict: {exchange: client_instance}
    """
    keys = _load_keys(live=live)
    clients = {}
    for exchange, cls in [("binance", BinanceClient), ("okx", OKXClient),
                           ("gate", GateClient), ("bitget", BitgetClient)]:
        k = keys.get(exchange, {})
        if not k.get("key"):
            logger.warning(f"[{exchange}] 未配置 API key，跳过")
            continue
        clients[exchange] = cls(live=live, keys=k, proxy=proxy)
        logger.info(f"[{exchange}] client 初始化 ({'主网' if live else '测试网'}"
                    f"{' proxy='+proxy if proxy else ''})")
    return clients
