"""
飞书群自定义机器人文本推送（msg_type: text）。

对齐常见自定义机器人习惯：若群开启「关键词」校验，正文需含「【机器人】」（发送前自动补上）。

默认 Webhook / Authorization 与参考项目 `cross_platform_arbitrage_system_livetrading` 的
`feishu_push.rs` 一致；可通过环境变量覆盖：
  FEISHU_WEBHOOK
  FEISHU_BOT_AUTHORIZATION

仅在主网实盘（调用方传入 live=True，即 `python main.py --live`）时发送；
`python main.py` Demo/测试网 **不推送**。失败只打日志，不抛异常、不阻塞主流程。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)

KEYWORD = "【机器人】"
STRATEGY_LINE = "【价差策略】Spread Hunter — 跨所价差套利"

FEISHU_TIMEOUT_S = 15

# 与参考 Rust 项目 feishu_push.rs 默认一致（可被环境变量覆盖）
DEFAULT_FEISHU_WEBHOOK = (
    "https://open.feishu.cn/open-apis/bot/v2/hook/646392d3-c205-41fc-b7c0-01a342eac341"
)
DEFAULT_FEISHU_AUTHORIZATION = "tooilGCilgCxxhlub0Qtbb"


def _feishu_webhook() -> str:
    return (os.environ.get("FEISHU_WEBHOOK") or DEFAULT_FEISHU_WEBHOOK).strip()


def _feishu_authorization() -> str:
    return (
        os.environ.get("FEISHU_BOT_AUTHORIZATION") or DEFAULT_FEISHU_AUTHORIZATION
    ).strip()


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def push_text(body: str, *, live: bool) -> None:
    if not live:
        return
    webhook = _feishu_webhook()
    if not webhook:
        logger.debug("[feishu] Webhook 为空，跳过推送")
        return

    body = (body or "").strip().replace("\r", "")
    if not body:
        logger.debug("[feishu] 正文为空，跳过")
        return
    if len(body) > 7500:
        body = body[:7500] + "\n...(truncated)"

    inner = body if KEYWORD in body else f"{KEYWORD}\n{body}"
    text = f"{STRATEGY_LINE}\n{inner}"

    payload = json.dumps(
        {"msg_type": "text", "content": {"text": text}},
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    auth = _feishu_authorization()
    if auth:
        req.add_header("Authorization", auth)

    try:
        with urllib.request.urlopen(req, timeout=FEISHU_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
        if raw:
            logger.info("[feishu] %s", raw)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace").strip()
        logger.warning("[feishu] HTTP %s: %s", e.code, err_body)
    except Exception as e:
        logger.warning("[feishu] 请求失败: %s", e)


async def push_text_async(body: str, *, live: bool) -> None:
    if not live:
        return
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, lambda: push_text(body, live=True))
    except Exception as e:
        logger.warning("[feishu] async 调度失败: %s", e)


def format_trading_started(exchanges: tuple[str, ...]) -> str:
    ex_s = ", ".join(sorted(exchanges))
    return (
        f"事件: 开始交易\n"
        f"时间: {_now_str()}\n"
        f"已连接交易所: {ex_s}"
    )


def format_open_position(pos, anomaly_pct: float) -> str:
    sl = pos.small_leg
    bl = pos.big_leg
    return (
        f"事件: 开仓\n"
        f"时间: {_now_str()}\n"
        f"持仓ID: {pos.id}\n"
        f"标的: {pos.symbol}\n"
        f"大所: {pos.big_exchange} | 小所: {pos.small_exchange}\n"
        f"方向: {pos.direction}\n"
        f"开仓 anomaly: {anomaly_pct:+.4f}%\n"
        f"小所 {pos.small_exchange}: {sl.side} @{sl.entry_price:.6g}  oid={sl.order_id}\n"
        f"大所 {pos.big_exchange}: {bl.side} @{bl.entry_price:.6g}  oid={bl.order_id}\n"
        f"数量: {sl.size_base:.8g} base | 名义 small≈{sl.size_usdt:.4f}U big≈{bl.size_usdt:.4f}U"
    )


def format_close_position(pos, total_pnl_session: float) -> str:
    reason_cn = {
        "convergence": "收敛止盈",
        "stop_loss": "止损",
        "timeout": "超时兜底",
        "funding_exit": "资金费不利",
    }.get(pos.close_reason, pos.close_reason)
    hold_s = (pos.close_time - pos.open_time) if pos.close_time else pos.hold_seconds
    return (
        f"事件: 平仓\n"
        f"时间: {_now_str()}\n"
        f"持仓ID: {pos.id}\n"
        f"标的: {pos.symbol} | {pos.small_exchange}/{pos.big_exchange}\n"
        f"原因: {reason_cn} ({pos.close_reason})\n"
        f"持仓时长: {hold_s:.1f}s\n"
        f"平仓 PnL: {pos.close_pnl_pct:+.4f}%\n"
        f"本笔PnL: {pos.pnl_usdt:+.4f} USDT\n"
        f"本次运行累计PnL: {total_pnl_session:+.4f} USDT\n"
        f"平仓价: small@{pos.small_close_price:.6g} big@{pos.big_close_price:.6g}"
    )


def format_close_leg_failed(pos, failed_ex: str, err: str) -> str:
    return (
        f"事件: 警告 · 平仓单腿失败（需人工核对敞口）\n"
        f"时间: {_now_str()}\n"
        f"持仓ID: {pos.id}\n"
        f"标的: {pos.symbol}\n"
        f"失败所: {failed_ex}\n"
        f"错误: {err}"
    )
