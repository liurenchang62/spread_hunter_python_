"""
资金再平衡模块 — 共享数据结构、参数、算法。

设计原则：
  - 所有阈值均为比例，无绝对数值，适配任意资金规模。
  - "现金" = available_futures + spot（可立即动用的资金）。
  - "权益" = total_futures + spot（含已用保证金和未实现盈亏）。
  - 再平衡只操作"现金"的分布，不强制平仓。
"""

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trader.exchange_client import build_clients
from trader.config import (
    REBALANCE_FLOOR_PCT,
    REBALANCE_MIN_TRANSFER_PCT,
    REBALANCE_FEE_CEIL_PCT,
    REBALANCE_CONFIRM_TIMEOUT_S,
    CASH_RATIO_MIN,
    CASH_RATIO_RESUME,
)
from clients.withdrawal_addresses import (
    ADDRESSES, NETWORK_NAMES,
    get_deposit_address, get_supported_networks,
)

# ── 网络枚举（手续费经验排序：低→高） ──────────────────────────────────────────
NETWORK_PRIORITY = ["SOL", "BSC", "ARB", "TRX", "ETH"]
ALL_NETWORKS     = ["SOL", "BSC", "ARB", "TRX", "ETH", "AVAX", "OP"]
EXCHANGES        = ["binance", "okx", "gate", "bitget"]

# ── 颜色 ────────────────────────────────────────────────────────────────────────
R = "\033[31m"; G = "\033[32m"; Y = "\033[33m"
C = "\033[36m"; W = "\033[0m";  B = "\033[1m"


def ok(msg):   print(f"  {G}✓{W} {msg}")
def warn(msg): print(f"  {Y}⚠{W}  {msg}")
def err(msg):  print(f"  {R}✗{W} {msg}")
def info(msg): print(f"  {C}→{W} {msg}")
def hdr(msg):  print(f"\n{C}{B}{msg}{W}")
def sep(n=60): print(f"  {C}{'─'*n}{W}")


# ── 客户端 ───────────────────────────────────────────────────────────────────────

def load_live_clients() -> dict:
    clients = build_clients(live=True, proxy="")
    if not clients:
        err("无法加载实盘 API Key，请检查 clients/api_keys_live.py")
        sys.exit(1)
    return clients


async def close_all(clients: dict):
    for c in clients.values():
        try:
            await c.close()
        except Exception:
            pass


# ── 余额数据结构 ─────────────────────────────────────────────────────────────────

@dataclass
class ExchangeState:
    exchange:       str
    available:      float = 0.0   # 期货可用余额（get_balance）
    spot:           float = 0.0   # 现货可用余额（get_spot_balance）
    total_futures:  float = 0.0   # 期货总权益（get_total_balance：含保证金+未实现盈亏）

    @property
    def cash(self) -> float:
        """可用现金 = 期货可用 + 现货可用"""
        return self.available + self.spot

    @property
    def equity(self) -> float:
        """总权益 = 期货总权益 + 现货（现货本身全为现金）"""
        return self.total_futures + self.spot


async def _fetch_one(ex: str, client) -> ExchangeState:
    s = ExchangeState(exchange=ex)
    for attr, method in [
        ("available",     client.get_balance),
        ("spot",          client.get_spot_balance),
        ("total_futures", client.get_total_balance),
    ]:
        try:
            setattr(s, attr, await method())
        except Exception as e:
            warn(f"{ex}.{attr} 查询失败: {e}")
    return s


async def fetch_all_states(clients: dict) -> dict[str, ExchangeState]:
    """并发查询所有交易所完整状态（available + spot + total_futures）。"""
    results = await asyncio.gather(*[_fetch_one(ex, c) for ex, c in clients.items()])
    return {s.exchange: s for s in results}


# ── 手续费数据结构 ───────────────────────────────────────────────────────────────

@dataclass
class FeeInfo:
    network:  str
    fee:      Optional[float]   # None = 查询失败或网络不支持
    has_addr: bool = False      # 该所是否配置了该网络的收款地址

    @property
    def known(self) -> bool:
        return self.fee is not None


async def _fetch_fee(client, exchange: str, net: str) -> FeeInfo:
    has_addr = net in ADDRESSES.get(exchange, {})
    fee: Optional[float] = None
    # 始终请求 API：get_api_network_name 对未映射链会回退为内部名（如 ARB），避免误报 N/A
    try:
        fee = await client.get_withdrawal_fee(net)
    except Exception:
        pass
    return FeeInfo(network=net, fee=fee, has_addr=has_addr)


async def fetch_all_fees(clients: dict) -> dict[str, dict[str, FeeInfo]]:
    """
    并发查询所有交易所所有网络手续费。
    返回 {exchange: {network: FeeInfo}}
    """
    async def _one_exchange(ex: str, client) -> tuple[str, dict[str, FeeInfo]]:
        tasks = [_fetch_fee(client, ex, net) for net in ALL_NETWORKS]
        infos = await asyncio.gather(*tasks)
        return ex, {fi.network: fi for fi in infos}

    pairs = await asyncio.gather(*[_one_exchange(ex, c) for ex, c in clients.items()])
    return dict(pairs)


# ── 触发条件 ─────────────────────────────────────────────────────────────────────

@dataclass
class RebalanceCheck:
    """再平衡检查结果。"""
    should_rebalance: bool
    total_cash:  float
    target_cash: float          # = total_cash / N（均值）
    floor_cash:  float          # = total_cash × FLOOR_PCT
    sinks:   list[str]          # 低于 floor 的交易所（需要补充）
    sources: list[str]          # 高于 target 的交易所（可作来源，按余额降序）
    reason:  str = ""


@dataclass
class LiquidityCheck:
    """整体流动性检查结果。"""
    cash_ratio:  float          # total_cash / total_equity
    total_cash:  float
    total_equity: float
    monitor_only: bool          # True = 低于 CASH_RATIO_MIN
    recovering:   bool          # True = 在 monitor_only 模式中，但已超过 RESUME 线
    reason:  str = ""


def check_rebalance(states: dict[str, ExchangeState]) -> RebalanceCheck:
    """
    检查单所再平衡触发条件：
      任意交易所 cash < total_cash × FLOOR_PCT → 触发

    逻辑：
      target = total_cash / N（均分，各所均等）
      floor  = total_cash × FLOOR_PCT
      sinks  = 所有低于 floor 的交易所（按缺口从大到小排序）
      sources= 所有高于 target 的交易所（按余额从多到少排序）
    """
    if not states:
        return RebalanceCheck(False, 0, 0, 0, [], [], "无数据")

    n          = len(states)
    total_cash = sum(s.cash for s in states.values())
    target     = total_cash / n
    floor      = total_cash * REBALANCE_FLOOR_PCT

    sinks = sorted(
        [ex for ex, s in states.items() if s.cash < floor],
        key=lambda ex: states[ex].cash,
    )
    sources = sorted(
        [ex for ex, s in states.items() if s.cash > target],
        key=lambda ex: states[ex].cash,
        reverse=True,
    )

    if not sinks:
        richest  = max(states, key=lambda ex: states[ex].cash)
        shortfall = states[richest].cash - floor
        return RebalanceCheck(
            False, total_cash, target, floor, [], [],
            f"所有交易所现金 ≥ floor（{floor:.2f}U）"
            f"，最富裕所: {richest}（{states[richest].cash:.2f}U）"
        )

    return RebalanceCheck(True, total_cash, target, floor, sinks, sources)


def check_liquidity(
    states: dict[str, ExchangeState],
    currently_monitor_only: bool,
) -> LiquidityCheck:
    """
    检查整体流动性：
      cash_ratio = total_cash / total_equity

    迟滞逻辑：
      进入 monitor_only: cash_ratio < CASH_RATIO_MIN
      退出 monitor_only: cash_ratio > CASH_RATIO_RESUME
    """
    if not states:
        return LiquidityCheck(0, 0, 0, False, False, "无数据")

    total_cash   = sum(s.cash   for s in states.values())
    total_equity = sum(s.equity for s in states.values())

    if total_equity == 0:
        return LiquidityCheck(0, total_cash, 0, False, False, "权益为零")

    ratio = total_cash / total_equity

    if currently_monitor_only:
        # 已在 monitor_only 中：只有超过 RESUME 才恢复
        monitor_only = ratio <= CASH_RATIO_RESUME
        recovering   = ratio > CASH_RATIO_RESUME
    else:
        monitor_only = ratio < CASH_RATIO_MIN
        recovering   = False

    reason = (
        f"cash_ratio={ratio*100:.1f}%  "
        f"(现金{total_cash:.2f}U / 权益{total_equity:.2f}U)"
    )
    return LiquidityCheck(ratio, total_cash, total_equity, monitor_only, recovering, reason)


# ── 路径规划 ─────────────────────────────────────────────────────────────────────

@dataclass
class TransferPath:
    """一条完整的提现路径（直连或中转步骤一）。"""
    kind:         str     # "direct" | "hub"
    src:          str
    dst:          str     # 直连时=最终目标；中转时=hub
    final_dst:    str     # 最终目标（直连时同 dst）
    network:      str
    fee:          float   # 0.0 表示未知
    fee_known:    bool
    address:      str
    # 中转专用
    hub_network:  str   = ""
    hub_fee:      float = 0.0
    hub_fee_known: bool = False

    @property
    def total_fee(self) -> float:
        f1 = self.fee     if self.fee_known     else 1.0
        f2 = self.hub_fee if self.hub_fee_known else (1.0 if self.kind == "hub" else 0.0)
        return f1 + f2

    @property
    def label(self) -> str:
        f1 = f"{self.fee:.4f}" if self.fee_known else "≈1.0"
        if self.kind == "direct":
            return f"直连 {self.src}→{self.final_dst}({self.network}, fee={f1}U)"
        f2 = f"{self.hub_fee:.4f}" if self.hub_fee_known else "≈1.0"
        return (f"中转 {self.src}→{self.dst}({self.network},{f1}U)"
                f"→{self.final_dst}({self.hub_network},{f2}U) 共≈{self.total_fee:.4f}U")


def find_best_path(
    source: str,
    target: str,
    amount: float,
    all_fees: dict[str, dict[str, FeeInfo]],
) -> Optional[TransferPath]:
    """
    为 source→target 寻找最优提现路径（直连 + 所有 1-hop 中转）。

    筛选逻辑：
      1. 只接受有目标充值地址的网络
      2. 费率已知时：若 fee/amount > FEE_CEIL_PCT，拒绝该路径
      3. 在有效路径中：优先选总费用最低的；费用未知时排后
    """
    src_fees = all_fees.get(source, {})
    candidates: list[TransferPath] = []

    # ── 直连路径 ──────────────────────────────────────────────────────────────
    for net in NETWORK_PRIORITY:
        if net not in get_supported_networks(source, target):
            continue
        addr = get_deposit_address(target, net)
        if not addr:
            continue
        fi  = src_fees.get(net)
        fee = fi.fee if (fi and fi.fee is not None) else None
        if fee is not None and amount > 0 and fee / amount > REBALANCE_FEE_CEIL_PCT:
            continue   # 手续费占比超限，放弃
        candidates.append(TransferPath(
            kind="direct", src=source, dst=target, final_dst=target,
            network=net, fee=fee or 0.0, fee_known=fee is not None,
            address=addr,
        ))

    # ── 中转路径（1-hop via hub） ──────────────────────────────────────────────
    for hub in EXCHANGES:
        if hub in (source, target):
            continue
        hub_fees = all_fees.get(hub, {})

        # 第一跳：source → hub
        best1: Optional[tuple[str, float, bool, str]] = None   # (net, fee, known, addr)
        for net in NETWORK_PRIORITY:
            if net not in get_supported_networks(source, hub):
                continue
            addr = get_deposit_address(hub, net)
            if not addr:
                continue
            fi  = src_fees.get(net)
            fee = fi.fee if (fi and fi.fee is not None) else None
            if fee is not None and amount > 0 and fee / amount > REBALANCE_FEE_CEIL_PCT:
                continue
            if best1 is None or (fee is not None and (not best1[2] or fee < best1[1])):
                best1 = (net, fee or 0.0, fee is not None, addr)
        if best1 is None:
            continue

        # 第二跳：hub → target
        best2: Optional[tuple[str, float, bool]] = None   # (net, fee, known)
        for net in NETWORK_PRIORITY:
            if net not in get_supported_networks(hub, target):
                continue
            addr2 = get_deposit_address(target, net)
            if not addr2:
                continue
            fi2  = hub_fees.get(net)
            fee2 = fi2.fee if (fi2 and fi2.fee is not None) else None
            if best2 is None or (fee2 is not None and (not best2[2] or fee2 < best2[1])):
                best2 = (net, fee2 or 0.0, fee2 is not None)
        if best2 is None:
            continue

        candidates.append(TransferPath(
            kind="hub", src=source, dst=hub, final_dst=target,
            network=best1[0], fee=best1[1], fee_known=best1[2], address=best1[3],
            hub_network=best2[0], hub_fee=best2[1], hub_fee_known=best2[2],
        ))

    if not candidates:
        return None

    # 排序：费用已知优先，总费用升序，直连优先（同费时）
    def _key(p: TransferPath):
        return (not p.fee_known, p.total_fee, p.kind != "direct")

    candidates.sort(key=_key)
    return candidates[0]


# ── 转账量计算 ───────────────────────────────────────────────────────────────────

@dataclass
class Transfer:
    """一笔完整的再平衡转账动作。"""
    source:   str
    target:   str
    amount:   float           # 本次提现金额（USDT）
    path:     TransferPath


def plan_transfers(
    check: RebalanceCheck,
    states: dict[str, ExchangeState],
    all_fees: dict[str, dict[str, FeeInfo]],
) -> list[Transfer]:
    """
    为所有 sink 计算最优转账计划。

    策略：
      每个 sink 的目标是到达 target（均值）。
      从 sources 按余额降序凑足，每个 source 最多转出至 floor 为止。
      如果所有 source 加总也不够，部分补充并告警。
      单笔金额 < MIN_TRANSFER_PCT × total_cash 的跳过（防微小操作）。
    """
    transfers: list[Transfer] = []
    min_transfer = check.total_cash * REBALANCE_MIN_TRANSFER_PCT

    # 工作副本（避免修改原始状态）
    working_cash = {ex: s.cash for ex, s in states.items()}

    for sink in check.sinks:
        needed = check.target_cash - working_cash[sink]
        if needed < min_transfer:
            info(f"→ {sink}: 缺口 {needed:.2f}U < 最小转账 {min_transfer:.2f}U，跳过")
            continue

        remaining = needed
        for src in check.sources:
            if working_cash.get(src, 0) <= check.floor_cash:
                continue   # 来源已无余量
            can_send = working_cash[src] - check.floor_cash
            send_now = min(can_send, remaining)
            if send_now < min_transfer:
                continue

            path = find_best_path(src, sink, send_now, all_fees)
            if path is None:
                warn(f"  {src}→{sink}: 无可用提现路径")
                continue

            transfers.append(Transfer(source=src, target=sink, amount=send_now, path=path))
            working_cash[src] -= send_now
            remaining -= send_now

            if remaining < min_transfer:
                break

        if remaining >= min_transfer:
            warn(f"→ {sink}: 仍缺 {remaining:.2f}U（所有来源余量不足）")

    return transfers
