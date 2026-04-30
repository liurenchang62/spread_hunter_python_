"""临时脚本：平仓 Gate BSB 空单，用完即删"""
import asyncio, sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

async def main():
    from trader.exchange_client import GateClient
    from clients.api_keys_live import get_live_keys

    gate = GateClient(live=True, keys=get_live_keys("gate"))
    try:
        res = await gate.place_order(
            symbol="BSB_USDT", side="buy",
            target_qty=1, ref_price=0.57,
            symbol_info=None, reduce_only=True,
        )
        if res.success:
            print(f"✓ Gate BSB空单已平 orderId={res.order_id}")
        else:
            print(f"✗ 失败: {res.error}")
    finally:
        await gate.close()

asyncio.run(main())
