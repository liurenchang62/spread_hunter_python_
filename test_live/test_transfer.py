"""
实盘资金划转测试：合约账户 → 现货/资金账户（小额）。

⚠️  涉及真实资金转移。默认 dry-run（只显示计划），加 --execute 才实际划转。

建议金额：10 USDT（大于各所最小划转限额，又不影响合约保证金）。

用法：
    python -m test_live.test_transfer              # 干跑（不实际划转）
    python -m test_live.test_transfer --execute    # 实际执行（每所需确认）
    python -m test_live.test_transfer --ex gate --execute --amount 10
"""

import argparse
import asyncio

from test_live._common import *

DEFAULT_AMOUNT = 10.0   # USDT，各所通常最小划转 >= 1-5 USDT


async def _transfer_one(name: str, client, amount: float, execute: bool):
    section(f"{name.upper()} — 合约→现货划转 {amount} USDT")

    # 查询当前合约余额
    try:
        bal = await client.get_balance()
        info(f"合约可用余额: {bal:.4f} USDT")
        if bal < amount:
            warn(f"合约余额 {bal:.4f} < 划转金额 {amount}，跳过")
            return
    except Exception as e:
        warn(f"余额查询失败: {e}，继续尝试划转")

    if not execute:
        info(f"[DRY-RUN] 将划转 {amount} USDT 合约→现货/资金账户（未实际执行）")
        return

    # 实际划转
    money(f"划转 {amount} USDT  合约账户 → 现货/资金账户")
    try:
        ok_ = await client.transfer_to_spot(amount)
        if ok_:
            ok(f"划转成功！{amount} USDT 已转入现货/资金账户")
            # 查询划转后余额验证
            await asyncio.sleep(1.0)
            bal_after = await client.get_balance()
            spot_after = await client.get_spot_balance()
            info(f"划转后合约余额: {bal_after:.4f} USDT")
            info(f"划转后现货余额: {spot_after:.4f} USDT")
        else:
            fail(f"划转失败（API 返回 False）")
            if name == "binance":
                warn("Binance 划转需要 API Key 有'通用划转'权限，请在 Binance 后台确认")
    except Exception as e:
        fail(f"划转异常: {e}")


async def main(targets: list[str], amount: float, execute: bool):
    mode = f"{R}实际执行{W}" if execute else f"{G}干跑模式（仅显示计划）{W}"
    section(f"资金划转测试 — {mode}")

    clients = load_live_clients()
    if not clients:
        return

    print(f"\n  划转金额: {amount} USDT / 所（合约→现货）")

    if execute:
        if not confirm(f"将在各所划转 {amount} USDT（合约→现货/资金账户），确认执行？"):
            print("  已取消。")
            for c in clients.values(): await c.close()
            return

    for name, client in clients.items():
        if targets and name not in targets:
            continue
        if execute and not confirm_each(name, f"划转 {amount} USDT 合约→现货"):
            warn(f"{name.upper()} 跳过")
            continue
        try:
            await _transfer_one(name, client, amount, execute)
        except Exception as e:
            fail(f"{name} 划转测试异常: {e}")

    for c in clients.values():
        await c.close()

    if not execute:
        print(f"\n  使用 --execute 实际执行划转。\n")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="实盘资金划转测试")
    parser.add_argument("--ex",      help="只测某交易所")
    parser.add_argument("--execute", action="store_true", help="实际执行（默认干跑）")
    parser.add_argument("--amount",  type=float, default=DEFAULT_AMOUNT,
                        help=f"划转金额 USDT（默认 {DEFAULT_AMOUNT}）")
    args = parser.parse_args()
    asyncio.run(main([args.ex] if args.ex else [], args.amount, args.execute))
