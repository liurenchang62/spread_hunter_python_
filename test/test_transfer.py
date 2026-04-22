"""
测试期货账户 → 现货/资金账户划转（提币前置步骤）。

注意事项：
  - Binance 测试网：期货 key 与现货 key 独立，划转通常不可用（预期失败）
  - OKX Demo：交易账户 → 资金账户，Demo 环境支持
  - Gate 测试网：futures → spot 划转，测试网可能不支持
  - Bitget Demo：期货 → 现货，模拟环境可能不支持

建议：先用小额（默认 1 USDT）测试，确认成功后再操作大额。

用法：
    python -m test.test_transfer
    python -m test.test_transfer --ex okx
    python -m test.test_transfer --amount 5.0
"""
import argparse
import asyncio

from test._common import *

# 默认测试划转金额（USDT）
DEFAULT_AMOUNT = 1.0


async def _test_one(name: str, client, amount: float):
    print(f"\n  [{name.upper()}]")

    # 查询划转前余额
    try:
        bal_before = await client.get_balance()
        info(f"划转前余额: {bal_before:.4f} USDT")
    except Exception as e:
        warn(f"无法查询划转前余额: {e}")
        bal_before = None

    info(f"尝试划转 {amount} USDT 期货 → 现货/资金账户")
    try:
        success = await client.transfer_to_spot(amount)
        if success:
            ok("划转成功")
            # 查询划转后余额（可能延迟）
            await asyncio.sleep(1.0)
            bal_after = await client.get_balance()
            info(f"划转后余额: {bal_after:.4f} USDT")
            if bal_before is not None:
                diff = bal_before - bal_after
                info(f"余额变化: -{diff:.4f} USDT")
        else:
            warn(f"划转返回失败（可能测试网不支持，或余额不足）")
    except NotImplementedError:
        fail("transfer_to_spot() 未实现")
    except Exception as e:
        fail(f"划转异常: {e}")


async def main(targets: list[str], amount: float):
    clients = load_clients()
    section(f"期货 → 现货划转测试（{amount} USDT）")

    warn("此操作会实际转移 Demo/Testnet 账户内的资金，测试网环境不影响真实资金")

    for name, client in clients.items():
        if targets and name not in targets:
            continue
        try:
            await _test_one(name, client, amount)
        except Exception as e:
            fail(f"{name} 划转测试异常: {e}")

    for c in clients.values():
        await c.close()
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="期货→现货划转（提币）测试")
    parser.add_argument("--ex",     help="只测某交易所")
    parser.add_argument("--amount", type=float, default=DEFAULT_AMOUNT,
                        help=f"划转金额 USDT（默认 {DEFAULT_AMOUNT}）")
    args = parser.parse_args()
    targets = [args.ex] if args.ex else []
    asyncio.run(main(targets, args.amount))
