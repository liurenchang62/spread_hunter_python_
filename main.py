"""
主入口：同时启动 Tracker（行情监控）+ Trader（下单执行）。

用法：
    python main.py          # 测试网/Demo（云服务器等直连交易所 API）
    python main.py --live   # 主网实盘（慎用！）

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
from rebalance.supervisor import RebalanceSupervisor

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


def _banner(live: bool) -> str:
    mode  = "\033[31m【主网实盘】\033[0m" if live else "\033[32m【测试网/Demo】\033[0m"
    return f"""
\033[36m╔══════════════════════════════════════════════════════════════╗
║         Spread Hunter  —  跨所价差套利系统                   ║
╚══════════════════════════════════════════════════════════════╝\033[0m
  模式    : {mode}
  资金    : 各所最小余额 × {trader_cfg.PAIR_CAPITAL_PCT*100:.1f}% / 对（两腿合计）
  开仓阈值: anomaly >= {trader_cfg.MIN_ANOMALY_TO_OPEN_PCT}%
  日止损  : 余额低于日初 × {trader_cfg.DAILY_HALT_PCT*100:.0f}% 停机
  风控    : 单所可用余额不足时该所仅平仓，不影响其他配对
  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""


async def _sweep_spot_to_futures():
    """启动时将各所现货余额自动划入期货账户。"""
    from trader.exchange_client import build_clients
    MIN_SWEEP = 0.5
    clients = build_clients(live=True, proxy="")
    try:
        for ex, client in clients.items():
            try:
                spot = await client.get_spot_balance()
                if spot < MIN_SWEEP:
                    logger.debug(f"[main] {ex} 现货余额 {spot:.2f}U，无需划转")
                    continue
                ok = await client.transfer_to_futures(spot)
                if ok:
                    logger.info(f"[main] {ex} 现货→期货划转 {spot:.2f}U 成功")
                else:
                    logger.warning(f"[main] {ex} 现货→期货划转失败，请手动检查")
            except Exception as e:
                logger.warning(f"[main] {ex} 划转异常: {e}")
    finally:
        for c in clients.values():
            try:
                await c.close()
            except Exception:
                pass


def _parse_position(ex: str, pos: dict, mi) -> tuple:
    """解析各所持仓格式，返回 (exchange_symbol, qty_base, close_side)。"""
    try:
        if ex == "binance":
            sym = pos.get("symbol", "")
            amt = float(pos.get("positionAmt", 0))
            return sym, abs(amt), "sell" if amt > 0 else "buy"
        elif ex == "okx":
            sym = pos.get("instId", "")
            contracts = abs(float(pos.get("pos", 0)))
            pos_side = pos.get("posSide", "long")
            side = "sell" if pos_side == "long" else "buy"
            sym_info = mi.get_symbol_info("okx", "TRXUSDT")
            ct_val = sym_info.native_ct_val if sym_info else 1.0
            return sym, contracts * ct_val, side
        elif ex == "gate":
            sym = pos.get("contract", "")
            size = float(pos.get("size", 0))
            sym_info = mi.get_symbol_info("gate", "TRXUSDT")
            ct_val = sym_info.native_ct_val if sym_info else 1.0
            return sym, abs(size) * ct_val, "sell" if size > 0 else "buy"
        elif ex == "bitget":
            sym = pos.get("symbol", "")
            total = float(pos.get("total", 0))
            hold_side = pos.get("holdSide", "long")
            return sym, total, "sell" if hold_side == "long" else "buy"
    except Exception:
        pass
    return "", 0.0, ""


async def _close_all_positions():
    """启动时关闭各所残留持仓（清理上次失败测试遗留的仓位，释放保证金）。"""
    from trader.exchange_client import build_clients
    from trader.market_info import MarketInfo, refresh_market_info

    clients = build_clients(live=True, proxy="")
    try:
        mi = MarketInfo()
        await refresh_market_info(mi, {"TRXUSDT"}, proxy="", live=True)

        any_found = False
        for ex, client in clients.items():
            try:
                positions = await client.get_positions()
                if not positions:
                    continue
                any_found = True
                logger.info(f"[main] {ex} 发现 {len(positions)} 个残留持仓，正在关闭…")
                for pos in positions:
                    sym, qty, side = _parse_position(ex, pos, mi)
                    if not sym or qty <= 0:
                        logger.warning(f"[main] {ex} 无法解析持仓: {pos}")
                        continue
                    logger.info(f"[main] {ex} 关闭持仓: {sym} qty={qty:.4f} → {side}")
                    sym_info = mi.get_symbol_info(ex, "TRXUSDT")
                    res = await client.place_order(
                        symbol=sym, side=side,
                        target_qty=qty, ref_price=0,
                        symbol_info=sym_info,
                        reduce_only=True,
                    )
                    if res.success:
                        logger.info(f"[main] {ex} 残留持仓关闭成功")
                    else:
                        logger.warning(f"[main] {ex} 残留持仓关闭失败: {res.error}")
            except Exception as e:
                logger.warning(f"[main] {ex} 查询/关闭持仓异常: {e}")

        if not any_found:
            logger.info("[main] 各所无残留持仓")
    finally:
        for c in clients.values():
            try:
                await c.close()
            except Exception:
                pass


async def _async_main(live: bool) -> int:
    global _EXIT_CODE

    trader_cfg.LIVE_TRADING_ON = live

    print(_banner(live))

    # ── 实盘启动前维护（sweep + 残留持仓清理）──────────────────────────────
    if live:
        # Step 1: 现货→期货自动划转
        logger.info("[main] 检查现货余额并自动划转至期货账户…")
        await _sweep_spot_to_futures()

        # Step 2: 关闭残留持仓（释放被占用的保证金）
        logger.info("[main] 检查并关闭各所残留持仓…")
        await _close_all_positions()

    # ── 初始化 ────────────────────────────────────────────────────────────────
    tracker    = Tracker()
    trader     = Trader(tracker)
    supervisor = RebalanceSupervisor(trader.risk) if live else None

    # ── 优雅退出处理 ──────────────────────────────────────────────────────────
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _handle_signal():
        if not stop_event.is_set():
            print("\n\033[33m收到退出信号，正在优雅关闭…\033[0m")
            stop_event.set()
            tracker.stop()
            trader.stop()
            if supervisor:
                supervisor.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except (NotImplementedError, AttributeError):
            pass   # Windows 不支持 add_signal_handler

    # ── 并发运行 ──────────────────────────────────────────────────────────────
    tasks = [
        asyncio.create_task(tracker.start(),    name="tracker"),
        asyncio.create_task(trader.start(),     name="trader"),
    ]
    if supervisor:
        tasks.append(asyncio.create_task(supervisor.start(), name="supervisor"))

    tracker_task = tasks[0]
    trader_task  = tasks[1]

    try:
        done, pending = await asyncio.wait(
            tasks,
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
        # 确保所有组件都停止
        tracker.stop()
        trader.stop()
        if supervisor:
            supervisor.stop()

        # 等待任务彻底结束（最多 10s）
        remaining = [t for t in tasks if not t.done()]
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
    args = parser.parse_args()

    if args.live:
        # ── Step 1: 只读检查（自动，无确认）─────────────────────────────────
        print("\033[36m正在运行启动前检查（只读，无资金操作）…\033[0m\n")
        from test_live.preflight import run_readonly
        readonly_ok = asyncio.run(run_readonly())

        # ── Step 2: 单次确认（含授权后续下单测试）──────────────────────────
        if readonly_ok:
            prompt = (
                "\033[32m只读检查全部通过。\033[0m\n"
                "即将划转现货余额、清理残留持仓并\033[31m启动实盘交易\033[0m。\n"
                "请输入 YES 确认: "
            )
        else:
            prompt = (
                "\033[31m部分只读检查失败，请确认问题后再决定是否继续。\n"
                "输入 YES 强制继续（实盘），其他取消: \033[0m"
            )
        if input(prompt).strip() != "YES":
            print("已取消。")
            return

    try:
        exit_code = asyncio.run(_async_main(live=args.live))
    except KeyboardInterrupt:
        exit_code = 0

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
