"""
一键将各交易所现货/资金账户的 USDT 全部划入期货账户。

适用场景：
  - 充值到账后手动补划（自动再平衡已内置此步骤）
  - 初始化：将 USDT 从现货划入期货账户准备交易

用法：
    python -m tools.sweep_to_futures          # 全部 4 所
    python -m tools.sweep_to_futures --ex gate okx
    python -m tools.sweep_to_futures --dry-run  # 只查看不划转
"""

import argparse
import asyncio
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

EXCHANGES = ["binance", "okx", "gate", "bitget"]
MIN_SWEEP = 0.5   # 低于此值不划转（避免手续费损耗）

G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; C = "\033[36m"; W = "\033[0m"; B = "\033[1m"


async def _sweep_one(ex: str, keys: dict, dry_run: bool) -> dict:
    from trader.exchange_client import BinanceClient, OKXClient, GateClient, BitgetClient
    cls_map = {"binance": BinanceClient, "okx": OKXClient,
               "gate": GateClient, "bitget": BitgetClient}
    client = cls_map[ex](live=True, keys=keys)
    result = {"ex": ex, "earned": 0.0, "spot_before": 0.0, "futures_before": 0.0,
              "swept": 0.0, "ok": None, "error": None}
    try:
        # Step 1: 赎回理财 → 现货/资金账户
        if not dry_run:
            earned = await client.redeem_earn()
            result["earned"] = earned
            if earned > 0.01:
                await asyncio.sleep(2)  # 等待到账

        # Step 2: 查询现货/期货余额
        spot, futures = await asyncio.gather(
            client.get_spot_balance(),
            client.get_balance(),
            return_exceptions=True,
        )
        result["spot_before"]    = spot    if isinstance(spot,    float) else 0.0
        result["futures_before"] = futures if isinstance(futures, float) else 0.0

        if result["spot_before"] < MIN_SWEEP:
            result["ok"] = "skip"
            return result

        if dry_run:
            result["ok"] = "dry"
            result["swept"] = result["spot_before"]
            return result

        # Step 3: 划转到期货账户
        ok = await client.transfer_to_futures(result["spot_before"])
        result["ok"]    = "ok" if ok else "fail"
        result["swept"] = result["spot_before"] if ok else 0.0
    except Exception as e:
        result["error"] = str(e)
        result["ok"] = "error"
    finally:
        await client.close()
    return result


async def _main(exchanges: list[str], dry_run: bool):
    from clients.api_keys_live import get_live_keys

    tag = f"{Y}[DRY RUN]{W} " if dry_run else ""
    print(f"\n{C}{B}{'═'*60}{W}")
    print(f"{C}{B}  {tag}现货 → 期货划转{W}")
    print(f"{C}{B}{'═'*60}{W}\n")

    tasks = {}
    for ex in exchanges:
        keys = get_live_keys(ex)
        if not keys or not keys.get("key"):
            print(f"  {Y}[skip]{W} {ex}: 未配置实盘 API Key")
            continue
        tasks[ex] = _sweep_one(ex, keys, dry_run)

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    total_swept = 0.0
    print(f"  {'交易所':<10} {'理财赎回':>10} {'现货余额':>10} {'合约余额':>10} {'划转':>10} {'状态'}")
    print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*6}")
    for r in results:
        if isinstance(r, Exception):
            print(f"  {'?':<10} {'':>10} {'':>10} {'':>10} {'':>10} {R}异常: {r}{W}")
            continue
        ex     = r["ex"]
        earned = r.get("earned", 0.0)
        spot   = r["spot_before"]
        fut    = r["futures_before"]
        swept  = r["swept"]
        status = r["ok"]
        total_swept += swept

        earned_s = f"{G}{earned:>10.2f}{W}" if earned > 0 else f"{'0.00':>10}"

        if status == "skip":
            flag = f"{C}─ 无需划转（< {MIN_SWEEP}U）{W}"
        elif status == "dry":
            flag = f"{Y}预计划转 {swept:.2f}U{W}"
        elif status == "ok":
            flag = f"{G}✓ 成功{W}"
        elif status == "fail":
            flag = f"{R}✗ 失败{W}"
        else:
            flag = f"{R}异常: {r.get('error', '')}{W}"

        print(f"  {ex:<10} {earned_s} {spot:>10.2f} {fut:>10.2f} {swept:>10.2f}  {flag}")

    print(f"\n  {'合计划转':<20} {total_swept:.2f} USDT")
    if dry_run:
        print(f"\n  {Y}以上为预览，实际未执行。去掉 --dry-run 参数后执行划转。{W}")
    print()


def main():
    ap = argparse.ArgumentParser(description="将各所现货 USDT 划入期货账户")
    ap.add_argument("--ex",      nargs="+", default=EXCHANGES, help="指定交易所")
    ap.add_argument("--dry-run", action="store_true",          help="只查看，不执行划转")
    args = ap.parse_args()
    asyncio.run(_main(args.ex, args.dry_run))


if __name__ == "__main__":
    main()
