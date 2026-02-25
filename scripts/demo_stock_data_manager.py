#!/usr/bin/env python3
"""Demo for stock_data.StockDataManager."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stock_data import StockDataManager


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Demo StockDataManager")
    p.add_argument("--codes", nargs="+", default=["600519", "002202"])
    p.add_argument("--daily-start", default="2026-02-20")
    p.add_argument("--daily-end", default="2026-02-25")
    p.add_argument("--minute-period", default="5")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    mgr = StockDataManager()

    print("=== Daily Batch ===")
    daily_df = mgr.get_daily_batch(codes=args.codes, start=args.daily_start, end=args.daily_end)
    print(daily_df.tail(10).to_string(index=False) if not daily_df.empty else "(empty)")

    for code in args.codes:
        print(f"\n=== Minute {code} ({args.minute_period}m) ===")
        try:
            minute_df = mgr.get_minute(code=code, period=args.minute_period)
            print(minute_df.tail(10).to_string(index=False) if not minute_df.empty else "(empty)")
        except Exception as exc:
            print(f"minute fetch failed: {exc}")

    print("\n=== Health Report ===")
    print(json.dumps(mgr.health_report(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
