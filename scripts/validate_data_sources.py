#!/usr/bin/env python3
"""Validate availability of common trading data sources.

Checks:
- baostock: login + fetch one day for sh.600519
- pytdx: connect to a common HQ server + fetch one bar
- Optional imports: adata / ashare / backtrader

Always exits with code 0, even when checks fail.
"""

from __future__ import annotations

import contextlib
import importlib
import socket
import sys
from typing import List, Tuple


Result = Tuple[str, bool, str]


def fmt_result(name: str, ok: bool, detail: str) -> str:
    status = "PASS" if ok else "FAIL"
    return f"[{status}] {name}: {detail}"


def check_baostock() -> Result:
    name = "baostock"
    try:
        bs = importlib.import_module("baostock")
    except Exception as exc:
        return name, False, f"import error: {exc}"

    lg = None
    try:
        lg = bs.login()
        if getattr(lg, "error_code", "1") != "0":
            return name, False, f"login failed: {getattr(lg, 'error_msg', 'unknown')}"

        rs = bs.query_history_k_data_plus(
            "sh.600519",
            "date,code,open,high,low,close,volume",
            start_date="2024-01-02",
            end_date="2024-01-02",
            frequency="d",
            adjustflag="3",
        )
        if getattr(rs, "error_code", "1") != "0":
            return name, False, f"query failed: {getattr(rs, 'error_msg', 'unknown')}"

        rows = []
        while rs.next():
            rows.append(rs.get_row_data())

        if not rows:
            return name, False, "query succeeded but no rows returned"
        return name, True, f"login+query ok, got {len(rows)} row(s), sample date={rows[0][0]}"
    except Exception as exc:
        return name, False, f"runtime error: {exc}"
    finally:
        with contextlib.suppress(Exception):
            if lg is not None:
                bs.logout()


def check_pytdx() -> Result:
    name = "pytdx"
    try:
        api_mod = importlib.import_module("pytdx.hq")
        params_mod = importlib.import_module("pytdx.params")
    except Exception as exc:
        return name, False, f"import error: {exc}"

    TdxHq_API = getattr(api_mod, "TdxHq_API", None)
    TDXParams = getattr(params_mod, "TDXParams", None)
    if TdxHq_API is None or TDXParams is None:
        return name, False, "missing TdxHq_API or TDXParams"

    # Commonly reachable public HQ nodes.
    servers = [
        ("119.147.212.81", 7709),
        ("14.215.128.18", 7709),
        ("60.191.117.167", 7709),
    ]

    last_err = ""
    for host, port in servers:
        api = TdxHq_API(heartbeat=True, auto_retry=True, multithread=False)
        try:
            # Quick DNS/TCP sanity before API connect.
            with socket.create_connection((host, port), timeout=3):
                pass

            ok = api.connect(host, port, time_out=3)
            if not ok:
                last_err = f"connect returned False for {host}:{port}"
                continue

            bars = api.get_security_bars(
                TDXParams.KLINE_TYPE_DAILY,
                1,  # 1 = SH
                "600519",
                0,
                1,
            )
            if not bars:
                last_err = f"connected {host}:{port}, but no bars returned"
                continue

            first = bars[0]
            dt = first.get("datetime") if hasattr(first, "get") else str(first)
            return name, True, f"connected {host}:{port}, fetched 1 bar (datetime={dt})"
        except Exception as exc:
            last_err = f"{host}:{port} error: {exc}"
        finally:
            with contextlib.suppress(Exception):
                api.disconnect()

    return name, False, last_err or "all servers failed"


def check_optional_import(module_name: str) -> Result:
    name = f"optional:{module_name}"
    try:
        importlib.import_module(module_name)
        return name, True, "import ok"
    except Exception as exc:
        return name, False, f"import error: {exc}"


def main() -> int:
    results: List[Result] = []
    results.append(check_baostock())
    results.append(check_pytdx())

    for mod in ("adata", "ashare", "backtrader"):
        results.append(check_optional_import(mod))

    for name, ok, detail in results:
        print(fmt_result(name, ok, detail))

    # Explicitly always return success for diagnostics-style usage.
    return 0


if __name__ == "__main__":
    sys.exit(main())
