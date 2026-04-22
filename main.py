"""
主入口：同时启动 Tracker（行情监控）+ Trader（下单执行）。

用法：
    python main.py                           # 测试网，自动读 PROXY_URL
    python main.py --proxy http://127.0.0.1:7897
    python main.py --live                    # 主网实盘（慎用！）
    python main.py --live --proxy ""         # 主网，无代理

退出码：
    0  — 正常退出（Ctrl+C 或 tracker 完成）
    1  — 日止损停机（daily_loss halt）
    2  — 未预期的异常
"""

import argparse
import asyncio
import logging
import signal
import sys
import time
from datetime import datetime

# Windows 终端强制 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from tracker.tracker import Tracker
from trader.trader import Trader
from trader import config as trader_cfg
from tracker import config as tracker_cfg

# ─── 日志 ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            trader_cfg.LOGS_DIR / "main.log", encoding="utf-8", errors="replace"
        ),
    ],
)
logger = logging.getLogger("main")

_EXIT_CODE = 0   # 由 daily_halt_monitor 设置


def _banner(live: bool, proxy: str) -> str:
    mode  = "\033[31m【主网实盘】\033[0m" if live else "\033[32m【测试网/Demo】\033[0m"
    proxy_s = proxy if proxy else "无"
    return f"""
\033[36m╔══════════════════════════════════════════════════════════════╗
║         Spread Hunter  —  跨所价差套利系统                   ║
╚══════════════════════════════════════════════════════════════╝\033[0m
  模式    : {mode}
  代理    : {proxy_s}
  资金    : 各所最小余额 × {trader_cfg.PAIR_CAPITAL_PCT*100:.1f}% / 对（两腿合计）
  开仓阈值: anomaly >= {trader_cfg.MIN_ANOMALY_TO_OPEN_PCT}%
  日止损  : 余额低于日初 × {trader_cfg.DAILY_HALT_PCT*100:.0f}% 停机
  最大敞口: 总余额 × {trader_cfg.MAX_EXPOSURE_PCT*100:.0f}%
  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""


async def _async_main(live: bool, proxy: str) -> int:
    global _EXIT_CODE

    # ── 覆盖配置（live / proxy 可由命令行覆盖 config.py 默认值）─────────────
    trader_cfg.LIVE_TRADING_ON = live
    if proxy:
        trader_cfg.PROXY_URL = proxy

    print(_banner(live, trader_cfg.PROXY_URL))

    # ── 初始化 ────────────────────────────────────────────────────────────────
    tracker = Tracker()
    trader  = Trader(tracker, proxy=trader_cfg.PROXY_URL)

    # ── 优雅退出处理 ──────────────────────────────────────────────────────────
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _handle_signal():
        if not stop_event.is_set():
            print("\n\033[33m收到退出信号，正在优雅关闭…\033[0m")
            stop_event.set()
            tracker.stop()
            trader.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except (NotImplementedError, AttributeError):
            pass   # Windows 不支持 add_signal_handler

    # ── 并发运行 ──────────────────────────────────────────────────────────────
    tracker_task = asyncio.create_task(tracker.start(), name="tracker")
    trader_task  = asyncio.create_task(trader.start(),  name="trader")

    try:
        done, pending = await asyncio.wait(
            [tracker_task, trader_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # 任一任务完成（trader 日止损退出 / tracker 退出 / 异常）→ 关闭另一个
        for task in done:
            exc = task.exception() if not task.cancelled() else None
            if exc:
                logger.error(f"[main] 任务 {task.get_name()} 异常退出: {exc}", exc_info=exc)
                _EXIT_CODE = 2

        # 检查是否是 daily_loss 停机
        if trader.risk.state.halted and trader.risk.state.halt_type == "daily_loss":
            logger.error("[main] 日止损停机，退出码=1")
            _EXIT_CODE = 1

        # 停止剩余任务
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[main] 未预期异常: {e}", exc_info=True)
        _EXIT_CODE = 2
    finally:
        # 确保 trader/tracker 都停止
        tracker.stop()
        trader.stop()

        # 等待任务彻底结束（最多 10s）
        remaining = [t for t in [tracker_task, trader_task] if not t.done()]
        if remaining:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*remaining, return_exceptions=True),
                    timeout=10.0,
                )
            except asyncio.TimeoutError:
                logger.warning("[main] 等待任务退出超时，强制结束")

        # 打印最终状态
        _print_final_summary(trader, tracker)

    return _EXIT_CODE


def _print_final_summary(trader: Trader, tracker: Tracker):
    rs = trader.risk.summary()
    print(f"""
\033[36m──────────── 运行摘要 ────────────\033[0m
  总开仓  : {trader._n_opened}
  总平仓  : {trader._n_closed}
  总PnL   : {trader._total_pnl:+.4f} USDT
  风控状态: {'停机[' + rs['halt_type'] + ']' if rs['halted'] else '正常'}
  余额    : {rs['balance']}
\033[36m──────────────────────────────────\033[0m
""")


def main():
    parser = argparse.ArgumentParser(
        description="Spread Hunter — 跨所价差套利系统"
    )
    parser.add_argument(
        "--live", action="store_true",
        help="主网实盘模式（默认为测试网/Demo）"
    )
    parser.add_argument(
        "--proxy", default=None, metavar="URL",
        help="HTTP 代理地址，例如 http://127.0.0.1:7897（留空则用 config.py 的 PROXY_URL）"
    )
    args = parser.parse_args()

    if args.live:
        confirm = input(
            "\033[31m警告：即将启动主网实盘模式，将使用真实资金！\n"
            "请输入 YES 确认: \033[0m"
        )
        if confirm.strip() != "YES":
            print("已取消。")
            return

    proxy = args.proxy if args.proxy is not None else trader_cfg.PROXY_URL

    try:
        exit_code = asyncio.run(_async_main(live=args.live, proxy=proxy))
    except KeyboardInterrupt:
        exit_code = 0

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
