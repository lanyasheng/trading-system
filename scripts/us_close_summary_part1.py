#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")

from scripts.us_market_night_v2 import build_report


def main() -> None:
    text = build_report().replace("完整美股夜盘复盘", "美股收盘总结（上）", 1)
    key = "\n5) **资金面（固定章节）**"
    if key in text:
        print(text.split(key)[0].rstrip())
    else:
        print(text)


if __name__ == "__main__":
    main()
