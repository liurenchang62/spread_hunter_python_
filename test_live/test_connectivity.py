"""
API 连通性检查（不涉及任何资金操作）。

检查项：
  - 各所 REST API 可达性（公开接口）
  - API Key 签名验证（通过余额查询接口）
  - 网络延迟粗估

用法：
    python -m test_live.test_connectivity
"""

import asyncio
import time

from test_live._common import *


async def _check_public(name: str, session) -> bool:
    """通过公开接口检查 REST 可达性。"""
    import aiohttp
    from clients.config import REST_BASE
    base = REST_BASE.get(name, "")
    if not base:
        warn(f"{name}: 无 REST 地址配置")
        return False

    # 各所公开接口
    public_paths = {
        "binance": "/fapi/v1/ping",
        "okx":     "/api/v5/public/time",
        "gate":    "/api/v4/futures/usdt/contracts?limit=1",
        "bitget":  "/api/v2/public/time",
    }
    path = public_paths.get(name, "/")
    url  = base + path

    t0 = time.monotonic()
    try:
        async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=5)) as r:
            await r.json()
        latency_ms = (time.monotonic() - t0) * 1000
        ok(f"{name.upper()} 公开接口: {latency_ms:.0f}ms  ({url})")
        return True
    except Exception as e:
        fail(f"{name.upper()} 公开接口不可达: {e}")
        return False


async def _check_auth(name: str, client) -> bool:
    """通过余额查询验证 API Key 签名。"""
    t0 = time.monotonic()
    try:
        bal = await client.get_balance()
        latency_ms = (time.monotonic() - t0) * 1000
        ok(f"{name.upper()} API Key 验证通过: 合约余额={bal:.4f} USDT  延迟={latency_ms:.0f}ms")
        return True
    except Exception as e:
        fail(f"{name.upper()} API Key 验证失败: {e}")
        return False


async def main():
    section("API 连通性检查（无资金操作）")

    import aiohttp
    clients = load_live_clients()
    if not clients:
        return

    # 公开接口检查
    print(f"\n  [公开接口]")
    async with aiohttp.ClientSession() as session:
        tasks = [_check_public(name, session) for name in clients]
        await asyncio.gather(*tasks)

    # API Key 签名验证
    print(f"\n  [API Key 验证]")
    for name, client in clients.items():
        await _check_auth(name, client)

    # 快速价格查询（验证市场数据可达）
    print(f"\n  [市场数据]")
    try:
        trx = await get_price("TRX")
        btc = await get_price("BTC")
        ok(f"TRX={trx:.6f} USDT  BTC={btc:.2f} USDT")
    except Exception as e:
        fail(f"价格查询失败: {e}")

    for c in clients.values():
        await c.close()
    print()


if __name__ == "__main__":
    asyncio.run(main())
