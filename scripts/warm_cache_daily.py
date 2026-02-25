#!/usr/bin/env python3
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stock_data import StockDataManager

WATCHLIST = [
    "600519", "000858", "002594", "002202", "601899", "000426", "601857",
    "159840", "515790", "516570", "515210", "518880",
]


def main() -> None:
    mgr = StockDataManager()
    end = date.today().strftime("%Y-%m-%d")
    start = (date.today() - timedelta(days=620)).strftime("%Y-%m-%d")

    ok = 0
    fail = 0
    for code in WATCHLIST:
        try:
            mgr.get_daily(code=code, start=start, end=end, adjust="qfq", use_cache=False)
            ok += 1
        except Exception:
            fail += 1
    print(f"cache_warm_done ok={ok} fail={fail}")


if __name__ == "__main__":
    main()
