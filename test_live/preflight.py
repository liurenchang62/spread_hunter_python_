"""
实盘启动前全面检查。

由 main.py --live 自动调用，也可单独运行查看结果：
    python -m test_live.preflight

检查顺序：
  [自动/只读]  1. API 连通性    — 公开接口延迟 + API Key 验证
  [自动/只读]  2. 账户余额      — 各所 USDT 余额是否充足
  [自动/只读]  3. 订单薄        — TRX 行情数据可达
  [自动/只读]  4. 合约规格      — 费率/规格信息可用
  [需确认/收费] 5. 限价单撤单   — 挂单验证（不成交，占用保证金几秒）
  [需确认/收费] 6. 市价下单     — 最小市价单（立即平仓，消耗少量手续费）

返回值（作为模块使用）：
  await run_readonly()      → bool  只跑 1-4
  await run_order_tests()   → bool  只跑 5-6（auto_confirm=True）
"""

import asyncio
import sys
import time
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from test_live._common import (
    G, R, Y, C, W, B,
    section, ok, fail, warn,
    reset_fail_count, get_fail_count,
)

EXCHANGES = ["binance", "okx", "gate", "bitget"]


async def _run_check(label: str, coro) -> int:
    """运行一项检查，返回该项的失败数。"""
    reset_fail_count()
    section(label)
    try:
        await coro
    except SystemExit:
        pass
    except Exception as e:
        fail(f"检查异常终止: {e}")
    return get_fail_count()


async def run_readonly() -> bool:
    """
    运行只读检查（1-4），无任何资金操作。
    返回 True = 全部通过，False = 有失败项。
    """
    from test_live import test_connectivity, test_account, test_orderbook, test_funding

    results: dict[str, int] = {}
    results["API 连通性"] = await _run_check(
        "1/4  API 连通性",
        test_connectivity.main(),
    )
    results["账户余额"] = await _run_check(
        "2/4  账户余额",
        test_account.main([]),
    )
    results["订单薄"] = await _run_check(
        "3/4  订单薄",
        test_orderbook.main([], ""),
    )
    results["合约规格"] = await _run_check(
        "4/4  合约规格 & 费率",
        test_funding.main([]),
    )

    _print_summary("只读检查结果", results)
    return all(v == 0 for v in results.values())


async def run_order_tests() -> bool:
    """
    运行下单验证（5-6），auto_confirm=True（调用方已取得用户确认）。
    返回 True = 全部通过，False = 有失败项。
    """
    from test_live import test_cancel, test_order

    results: dict[str, int] = {}
    results["限价单撤单"] = await _run_check(
        "5/6  限价单撤单（不成交）",
        test_cancel.main([], auto_confirm=True),
    )
    results["市价下单"] = await _run_check(
        "6/6  最小市价单（立即平仓）",
        test_order.main([], auto_confirm=True),
    )

    _print_summary("下单测试结果", results)
    return all(v == 0 for v in results.values())


def _print_summary(title: str, results: dict[str, int]) -> None:
    print(f"\n{C}{B}{'═'*56}{W}")
    print(f"{C}{B}  {title}{W}")
    print(f"{C}{B}{'═'*56}{W}")
    for name, n_fail in results.items():
        if n_fail == 0:
            print(f"  {G}[通过]{W}  {name}")
        else:
            print(f"  {R}[失败 {n_fail} 项]{W}  {name}")
    print(f"{C}{B}{'═'*56}{W}\n")


# ─── 单独运行入口 ──────────────────────────────────────────────────────────────

async def _standalone():
    t0 = time.monotonic()
    print(f"""
{C}{B}╔══════════════════════════════════════════════════════╗
║     Spread Hunter — 实盘启动前全面检查               ║
╚══════════════════════════════════════════════════════╝{W}
""")

    readonly_ok = await run_readonly()

    if not readonly_ok:
        print(f"{R}只读检查存在失败项，建议修复后再执行下单测试。{W}\n")
        yn = input("仍要继续下单测试？(yes/no): ")
        if yn.strip().lower() != "yes":
            print("已取消。")
            return

    print(f"\n{Y}{B}即将进行下单验证（将消耗少量手续费）。{W}")
    yn = input("输入 yes 继续，其他取消: ")
    if yn.strip().lower() != "yes":
        print("已跳过下单测试。")
        return

    await run_order_tests()

    elapsed = time.monotonic() - t0
    print(f"全部检查完成，耗时 {elapsed:.1f}s\n")


def main():
    asyncio.run(_standalone())


if __name__ == "__main__":
    main()
