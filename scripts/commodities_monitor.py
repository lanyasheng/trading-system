#!/usr/bin/env python3
"""商品与市场异动监控 - 基于 Yahoo Finance API"""

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.report_templates import get_template

DATA_DIR = Path("/tmp/commodities_data")
DATA_DIR.mkdir(exist_ok=True)
HISTORY_FILE = DATA_DIR / "yf_history.json"

WATCHLIST = {
    "GC=F":  {"name": "黄金",    "unit": "USD/oz", "threshold": 1.0},
    "SI=F":  {"name": "白银",    "unit": "USD/oz", "threshold": 1.5},
    "CL=F":  {"name": "原油(WTI)", "unit": "USD/bbl", "threshold": 1.5},
    "HG=F":  {"name": "铜",      "unit": "USD/lb",  "threshold": 1.5},
    "^GSPC": {"name": "标普500",  "unit": "pts",     "threshold": 1.0},
    "^IXIC": {"name": "纳斯达克", "unit": "pts",     "threshold": 1.2},
    "^DJI":  {"name": "道琼斯",   "unit": "pts",     "threshold": 1.0},
    "NVDA":  {"name": "英伟达",   "unit": "USD",     "threshold": 3.0},
    "AAPL":  {"name": "苹果",    "unit": "USD",     "threshold": 2.0},
    "MSFT":  {"name": "微软",    "unit": "USD",     "threshold": 2.0},
    "GOOGL": {"name": "谷歌",    "unit": "USD",     "threshold": 2.0},
    "META":  {"name": "Meta",    "unit": "USD",     "threshold": 2.5},
}

def fetch_quote(sym):
    url = "https://query2.finance.yahoo.com/v8/finance/chart/" + sym + "?interval=1d&range=5d"
    proxy_url = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}) if proxy_url else urllib.request.BaseHandler()
    opener = urllib.request.build_opener(handler)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = opener.open(req, timeout=10)
        data = json.loads(resp.read())
        r = data.get("chart", {}).get("result", [{}])[0]
        closes = r.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        valid = [c for c in closes if c is not None]
        if len(valid) >= 2:
            return {"current": valid[-1], "previous": valid[-2]}
    except Exception as e:
        print("  [ERR] " + sym + ": " + str(e), file=sys.stderr)
    return None

def main():
    now = datetime.now()
    alerts = []
    report_lines = []

    for sym, info in WATCHLIST.items():
        quote = fetch_quote(sym)
        if not quote:
            report_lines.append(info["name"] + " (" + sym + "): 数据获取失败")
            continue
        curr = quote["current"]
        prev = quote["previous"]
        chg = (curr - prev) / prev * 100
        line = info["name"] + ": " + str(round(curr, 2)) + " " + info["unit"] + " (" + (("+" if chg > 0 else "") + str(round(chg, 2))) + "%)"
        report_lines.append(line)

        if abs(chg) >= info["threshold"]:
            direction = "📈" if chg > 0 else "📉"
            alerts.append(direction + " " + info["name"] + ": " + str(round(curr, 2)) + " " + info["unit"] + " " + (("+" if chg > 0 else "") + str(round(chg, 2))) + "%")

    print("=== 市场行情 " + now.strftime("%Y-%m-%d %H:%M") + " ===")
    for line in report_lines:
        print("  " + line)

    if alerts:
        print("\n⚠️ 异动警报 (超过阈值):")
        for a in alerts:
            print("  " + a)

        tpl = get_template("anomaly")
        title = tpl["title"].format(time=now.strftime("%H:%M"))
        s = tpl["sections"]
        msg_lines = [
            title,
            "",
            s[0],
            "- 风险偏好：隔夜波动抬升，优先防守+确认后跟随。",
            "",
            s[1],
            *[f"- {x}" for x in alerts],
            "",
            s[2],
            "- 驱动：商品/美股关键标的达到预设阈值触发。",
            "",
            s[3],
            "- 影响：若异动延续，A股资源与成长板块开盘分化概率上升。",
            "",
            s[4],
            "- 建议：不追高，等开盘30分钟量能确认后再加仓。",
        ]
        return "\n".join(msg_lines)
    else:
        print("\n✅ 所有品种波动在阈值内")
        return "HEARTBEAT_OK"

if __name__ == "__main__":
    result = main()
    print("\n" + result)
