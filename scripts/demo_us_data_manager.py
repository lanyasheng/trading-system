#!/usr/bin/env python3
"""Demo for us_data.USDataManager."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from us_data import USDataManager


def main() -> None:
    symbols = ["AAPL", "NVDA", "TSLA", "BABA", "PDD", "NIO", "^GSPC", "^IXIC", "^DJI"]
    mgr = USDataManager()

    print("=== US Snapshots ===")
    df = mgr.get_snapshots(symbols=symbols)
    print(df.to_string(index=False) if not df.empty else "(empty)")

    print("\n=== Health Report ===")
    print(json.dumps(mgr.health_report(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
