"""
实盘资金费率拉取测试（公开接口，无资金风险）。

测试内容：
  - 从各所主网拉取合约规格（qty_step、min_qty、native_ct_val）
  - 拉取当前 8h 资金费率
  - 展示 taker 手续费率
  - 模拟预估: 持仓 60s 的资金费率成本（USDT）

用法：
    python -m test_live.test_funding
    python -m test_live.test_funding --ex binance
"""

import argparse
import asyncio

from test_live._common import *


async def main(targets: list[str]):
    section("资金费率 & 合约规格测试（公开接口，无资金风险）")

    print(f"\n  拉取市场信息（{TEST_SYMBOL_INTERNAL}）…")
    try:
        mi = await load_market_info({TEST_SYMBOL_INTERNAL})
        ok(f"市场信息拉取成功，共 {len(mi.symbol_info)} 条规格数据")
    except Exception as e:
        fail(f"市场信息拉取失败: {e}")
        return

    trx_price = await get_price("TRX")
    info(f"  TRX 当前价: {trx_price:.6f} USDT")

    for name in ["binance", "okx", "gate", "bitget"]:
        if targets and name not in targets:
            continue

        section(f"{name.upper()} — 费率 & 合约规格")

        # ── 合约规格 ──────────────────────────────────────────────────────────
        sym_info = mi.get_symbol_info(name, TEST_SYMBOL_INTERNAL)
        if sym_info:
            ok(f"合约规格已加载")
            info(f"  qty_step     = {sym_info.qty_step}")
            info(f"  min_qty      = {sym_info.min_qty}")
            info(f"  native_ct_val= {sym_info.native_ct_val}")
            qty, notional = compute_min_qty(mi, name, TEST_SYMBOL_INTERNAL, trx_price)
            info(f"  最小可下单量 = {qty} TRX ≈ {notional:.4f} USDT")
        else:
            warn(f"合约规格未加载（{TEST_SYMBOL_INTERNAL} 不在该所列表中或拉取失败）")

        # ── Taker 手续费 ──────────────────────────────────────────────────────
        taker_fee = mi.get_taker_fee(name)
        info(f"  Taker 手续费 = {taker_fee*100:.4f}%")

        # ── 资金费率 ──────────────────────────────────────────────────────────
        fr = mi.get_funding_rate(name, TEST_SYMBOL_INTERNAL)
        if fr != 0.0003:  # 0.0003 是默认兜底值
            ok(f"资金费率(8h) = {fr*100:.6f}%")
        else:
            warn(f"资金费率(8h) = {fr*100:.6f}% （使用默认保守估算值，实际可能不同）")

        # ── 成本估算（持仓 60s）──────────────────────────────────────────────
        if sym_info:
            qty, notional = compute_min_qty(mi, name, TEST_SYMBOL_INTERNAL, trx_price)
            hold_60s = 60.0
            fee_cost     = notional * taker_fee * 4              # 4 笔吃单（进出各两腿）
            funding_cost = notional * abs(fr) * hold_60s / 28800 # 持仓 60s 的资金费
            info(f"  ── 以最小下单量 {qty} TRX（{notional:.4f} USDT）持仓 60s 成本估算 ──")
            info(f"  手续费合计（4笔）= {fee_cost:.6f} USDT")
            info(f"  资金费（60s）    = {funding_cost:.6f} USDT")
            info(f"  成本合计         = {fee_cost+funding_cost:.6f} USDT")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="资金费率和合约规格测试")
    parser.add_argument("--ex", help="只测某交易所")
    args = parser.parse_args()
    asyncio.run(main([args.ex] if args.ex else []))
