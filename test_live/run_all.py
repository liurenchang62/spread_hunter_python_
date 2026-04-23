"""
实盘测试套件 — 顺序执行所有测试。

分为两组：
  [安全组] 只读/无资金风险，自动执行
    1. test_connectivity  — API 连通性 + Key 验证
    2. test_account       — 账户余额、持仓、挂单
    3. test_orderbook     — TRX 订单薄（公开接口）
    4. test_funding       — 资金费率 + 合约规格

  [资金组] 涉及真实资金，需要加 --money 才执行（每项独立确认）
    5. test_cancel        — 限价单挂单 + 撤单（低风险）
    6. test_order         — 最小市价单买卖（消耗手续费）
    7. test_transfer      — 合约→现货小额划转（需加 --transfer）

用法：
    python -m test_live.run_all              # 只跑安全组
    python -m test_live.run_all --money      # 包含资金组（test_cancel + test_order）
    python -m test_live.run_all --transfer   # 同时包含划转测试
    python -m test_live.run_all --ex gate    # 只测 gate
"""

import argparse
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

G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; C = "\033[36m"; W = "\033[0m"; B = "\033[1m"


async def run_safe(ex_filter: list[str]):
    """执行只读安全测试组。"""
    from test_live import test_connectivity, test_account, test_orderbook, test_funding
    print(f"\n{C}{B}{'='*56}{W}")
    print(f"{C}{B}  [1/4] 连通性检查{W}")
    print(f"{C}{B}{'='*56}{W}")
    await test_connectivity.main()

    print(f"\n{C}{B}{'='*56}{W}")
    print(f"{C}{B}  [2/4] 账户信息{W}")
    print(f"{C}{B}{'='*56}{W}")
    await test_account.main(ex_filter)

    print(f"\n{C}{B}{'='*56}{W}")
    print(f"{C}{B}  [3/4] 订单薄{W}")
    print(f"{C}{B}{'='*56}{W}")
    await test_orderbook.main(ex_filter, "")

    print(f"\n{C}{B}{'='*56}{W}")
    print(f"{C}{B}  [4/4] 资金费率 & 合约规格{W}")
    print(f"{C}{B}{'='*56}{W}")
    await test_funding.main(ex_filter)


async def run_money(ex_filter: list[str]):
    """执行资金组测试（限价单撤单 + 市价单）。"""
    from test_live import test_cancel, test_order
    print(f"\n{R}{B}{'='*56}{W}")
    print(f"{R}{B}  [5/6] 限价单撤单测试（低风险）{W}")
    print(f"{R}{B}{'='*56}{W}")
    await test_cancel.main(ex_filter)

    print(f"\n{R}{B}{'='*56}{W}")
    print(f"{R}{B}  [6/6] 最小市价单测试（消耗手续费）{W}")
    print(f"{R}{B}{'='*56}{W}")
    await test_order.main(ex_filter)


async def run_transfer(ex_filter: list[str]):
    """执行资金划转测试。"""
    from test_live import test_transfer
    print(f"\n{R}{B}{'='*56}{W}")
    print(f"{R}{B}  [7] 合约→现货划转测试{W}")
    print(f"{R}{B}{'='*56}{W}")
    await test_transfer.main(ex_filter, test_transfer.DEFAULT_AMOUNT, execute=False)


async def main_async(args):
    t0 = time.monotonic()

    print(f"""
{C}{B}╔══════════════════════════════════════════════════════╗
║     Spread Hunter — 实盘测试套件                     ║
╚══════════════════════════════════════════════════════╝{W}
  交易所过滤: {args.ex or '全部'}
  资金组测试: {'是' if args.money else '否（加 --money 启用）'}
  划转测试  : {'是' if args.transfer else '否（加 --transfer 启用）'}
""")

    ex_filter = [args.ex] if args.ex else []

    # ── 安全组（始终执行）────────────────────────────────────────────────────
    await run_safe(ex_filter)

    # ── 资金组（--money 时执行）──────────────────────────────────────────────
    if args.money:
        await run_money(ex_filter)

    # ── 划转测试（--transfer 时执行）─────────────────────────────────────────
    if args.transfer:
        await run_transfer(ex_filter)

    elapsed = time.monotonic() - t0
    print(f"\n{C}{B}{'='*56}{W}")
    print(f"{C}{B}  测试完成  耗时 {elapsed:.1f}s{W}")
    if not args.money:
        print(f"  {Y}提示: 加 --money 运行资金组测试（限价单撤单 + 最小市价单）{W}")
    print(f"{C}{B}{'='*56}{W}\n")


def main():
    parser = argparse.ArgumentParser(description="实盘测试套件")
    parser.add_argument("--ex",       help="只测某交易所: binance/okx/gate/bitget")
    parser.add_argument("--money",    action="store_true", help="包含资金组测试（市价单+撤单）")
    parser.add_argument("--transfer", action="store_true", help="包含划转测试（dry-run）")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
