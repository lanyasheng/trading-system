#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")

from scripts.us_market_night_v2 import build_report


def main() -> None:
    text = build_report().replace("完整美股夜盘复盘", "美股收盘总结（下）", 1)
    key = "\n5) **资金面（固定章节）**"
    if key in text:
        tail = key.strip("\n") + text.split(key, 1)[1]
    else:
        tail = text
    tail += (
        "\n\n8) **收盘后执行要点**\n"
        "- 优先复盘：AI/资源两条主线是否出现高位分歧。\n"
        "- 次日A股执行：不追高，开盘30分钟看量能确认后分批。\n"
        "- 风险控制：若隔夜期货/金属反向，先减仓再观察。"
    )
    print(tail)


if __name__ == "__main__":
    main()
