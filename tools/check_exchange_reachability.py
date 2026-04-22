#!/usr/bin/env python3
"""
从「当前这台机器」的出口 IP 探测四家交易所主网 REST 是否可达。

用于新 VPS（如东京）验收：SSH 登录后在本机执行：
    python3 tools/check_exchange_reachability.py

若某行 [FAIL]，请到该所 API 文档核对域名，或检查本地防火墙。
"""

from __future__ import annotations

import ssl
import sys
import urllib.error
import urllib.request

# 均为公开端点，无需 API Key
URLS: list[tuple[str, str]] = [
    ("binance", "https://fapi.binance.com/fapi/v1/ping"),
    ("okx", "https://www.okx.com/api/v5/public/time"),
    ("gate", "https://api.gateio.ws/api/v4/futures/usdt/contracts?limit=1"),
    ("bitget", "https://api.bitget.com/api/v2/public/time"),
]


def main() -> int:
    ctx = ssl.create_default_context()
    ua = "Mozilla/5.0 (compatible; SpreadHunter-Reachability/1.0)"
    ok_all = True
    for name, url in URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                code = resp.status
            print(f"[OK]   {name:8} HTTP {code}  {url}")
        except urllib.error.HTTPError as e:
            ok_all = False
            print(f"[FAIL] {name:8} HTTP {e.code}  {url}  ({e.reason})")
        except Exception as e:
            ok_all = False
            print(f"[FAIL] {name:8} {type(e).__name__}: {e}  {url}")
    if not ok_all:
        print("\n提示: Binance 若返回 451，多为机房地区限制，可换区或沿用 symbol_selector 的测试网回退逻辑。")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
