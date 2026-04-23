"""
顺序运行所有测试（余额 → 持仓 → 撤单 → 下单）。
不运行 test_transfer（涉及资金划转，需手动确认）。

用法：
    python -m test.run_all
    python -m test.run_all --ex okx
    python -m test.run_all --skip-orders    # 跳过实际下单
"""
import argparse
import asyncio
import sys
import time

from test_demo._common import section, warn, ok, fail, C, W

# 导入各测试模块的 main 函数
from test.test_balance   import main as run_balance
from test.test_positions import main as run_positions
from test.test_cancel    import main as run_cancel
from test.test_orders    import main as run_orders


async def run_all(targets: list[str], skip_orders: bool):
    t0 = time.monotonic()
    results: dict[str, str] = {}

    async def _run(label: str, coro):
        t = time.monotonic()
        try:
            await coro
            elapsed = time.monotonic() - t
            results[label] = f"OK  ({elapsed:.1f}s)"
        except Exception as e:
            elapsed = time.monotonic() - t
            results[label] = f"ERR ({elapsed:.1f}s): {e}"

    await _run("余额查询",   run_balance(targets))
    await _run("持仓查询",   run_positions(targets, ""))

    if not skip_orders:
        warn("即将执行限价撤单 & 市价下单测试（Demo/Testnet，不影响真实资金）")
        await _run("限价撤单",   run_cancel(targets))
        await _run("市价下单",   run_orders(targets, ""))
    else:
        results["限价撤单"] = "SKIP"
        results["市价下单"] = "SKIP"

    # ── 汇总
    total = time.monotonic() - t0
    print(f"\n{C}{'═'*52}")
    print(f"  测试汇总  (总耗时 {total:.1f}s)")
    print(f"{'═'*52}{W}")
    for label, status in results.items():
        color = "\033[32m" if status.startswith("OK") else (
                "\033[33m" if status.startswith("SKIP") else "\033[31m")
        print(f"  {color}{label:10s}{W}  {status}")
    print()

    if not skip_orders:
        warn("请确认 Demo/Testnet 账户无残留持仓（test_orders 会自动平仓）")

    print("※ 期货→现货划转测试需单独运行: python -m test.test_transfer")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="运行所有交易功能测试")
    parser.add_argument("--ex",          help="只测某交易所")
    parser.add_argument("--skip-orders", action="store_true",
                        help="跳过实际下单（不产生成交）")
    args = parser.parse_args()
    targets = [args.ex] if args.ex else []
    asyncio.run(run_all(targets, args.skip_orders))
