"""
测试各交易所余额查询。

用法：
    python -m test.test_balance
    python -m test.test_balance --ex okx
"""
import argparse
import asyncio

from test._common import *


async def main(targets: list[str]):
    clients = load_clients()
    section("余额查询测试（USDT 可用余额）")

    for name, client in clients.items():
        if targets and name not in targets:
            continue
        print(f"\n  [{name.upper()}]")
        try:
            bal = await client.get_balance()
            if bal > 0:
                ok(f"可用余额: {bal:.4f} USDT")
            else:
                warn(f"可用余额: {bal:.4f} USDT（余额为 0，请检查是否已充值测试资金）")
        except NotImplementedError:
            fail("get_balance() 未实现")
        except Exception as e:
            fail(f"查询失败: {e}")

    for c in clients.values():
        await c.close()

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="余额查询测试")
    parser.add_argument("--ex", help="只测某交易所: binance / okx / gate / bitget")
    args = parser.parse_args()
    targets = [args.ex] if args.ex else []
    asyncio.run(main(targets))
