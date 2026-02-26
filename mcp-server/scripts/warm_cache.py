#!/usr/bin/env python3
"""Pre-market cache warmup script.

Run daily before market open (~07:00) to ensure all watchlist stocks
have sufficient K-line data for technical analysis.

Usage:
    .venv/bin/python3 scripts/warm_cache.py [--days 90]
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data_sources.manager import DataManager
from config import get_workspace_root

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("warm-cache")


def load_watchlist():
    ws = get_workspace_root()
    wl_path = ws / "knowledge" / "watchlist.json"
    if not wl_path.exists():
        logger.error("Watchlist not found: %s", wl_path)
        return []

    with open(wl_path) as f:
        raw = json.load(f)

    codes = []
    for key in ("priority", "observe", "research"):
        for item in raw.get(key, []):
            code = item.get("code", "") if isinstance(item, dict) else str(item)
            code = code.strip()
            if len(code) == 6:
                codes.append(code)
    return codes


def main():
    parser = argparse.ArgumentParser(description="Warm K-line cache for watchlist")
    parser.add_argument("--days", type=int, default=90, help="Days of history to fetch")
    args = parser.parse_args()

    codes = load_watchlist()
    if not codes:
        logger.error("No codes to warm")
        return 1

    logger.info("Warming %d codes with %d days of history", len(codes), args.days)

    dm = DataManager()
    t0 = time.time()
    result = dm.warm_klines(codes, days=args.days)
    elapsed = time.time() - t0

    details = result.get("details", {})
    success = sum(1 for v in details.values() if isinstance(v, int) and v > 0)
    insufficient = sum(1 for v in details.values() if isinstance(v, int) and 0 < v < 20)
    failed = sum(1 for v in details.values() if isinstance(v, str))

    logger.info("Warmup complete in %.1fs", elapsed)
    logger.info("  Success: %d/%d", success, len(codes))
    if insufficient:
        logger.warning("  Insufficient (<20 rows): %d", insufficient)
    if failed:
        logger.error("  Failed: %d", failed)

    for code in sorted(details.keys()):
        rows = details[code]
        if isinstance(rows, int):
            status = "OK" if rows >= 20 else "LOW"
            logger.info("  %s: %d rows [%s]", code, rows, status)
        else:
            logger.error("  %s: %s [ERR]", code, rows)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
