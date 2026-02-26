#!/usr/bin/env python3
"""US market close summary (post-close) with full structure."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.us_market_night_v2 import build_report


def main() -> None:
    text = build_report()
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    # 标题从“夜盘复盘”调整为“收盘总结”
    text = text.replace("完整美股夜盘复盘", "美股收盘总结", 1)
    # 收盘执行补充
    text += (
        "\n\n8) **收盘后执行要点**\n"
        "- 优先复盘：AI/资源两条主线是否出现高位分歧。\n"
        "- 次日A股执行：不追高，开盘30分钟看量能确认后分批。\n"
        "- 风险控制：若隔夜期货/金属反向，先减仓再观察。"
    )
    print(text)


if __name__ == "__main__":
    main()
