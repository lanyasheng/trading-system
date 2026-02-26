#!/usr/bin/env python3
"""商品与市场异动监控 - 基于 Yahoo Finance API

优化：
1. 变化检测：只有异动清单变化时才发送
2. 时段区分：美股常规/盘前盘后
3. A股时段：美股数据稳定，仅重大变化才发送
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.report_templates import get_template

DATA_DIR = Path("/tmp/commodities_data")
DATA_DIR.mkdir(exist_ok=True)
HISTORY_FILE = DATA_DIR / "yf_history.json"
STATE_FILE = DATA_DIR / "commodities_state.json"

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

def get_us_market_period():
    """判断当前美股时段

    返回:
    - 'regular': 美股常规交易时段 (21:30-04:00 北京时间)
    - 'premarket': 盘前 (16:00-21:30)
    - 'afterhours': 盘后 (04:00-08:00)
    - 'closed': 休市
    """
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    weekday = now.weekday()

    # 周末休市
    if weekday >= 5:
        return 'closed'

    # 北京时间对应美股时段
    # 美股常规: 21:30-04:00 (北京时间)
    if (hour >= 21 and hour <= 23) or (hour >= 0 and hour < 4) or (hour == 4 and minute == 0):
        return 'regular'
    # 盘前: 16:00-21:30
    elif hour >= 16 and hour < 21:
        return 'premarket'
    # 盘后: 04:00-08:00
    elif hour >= 4 and hour < 8:
        return 'afterhours'
    else:
        return 'closed'

def is_ashare_trading():
    """判断是否A股交易时段"""
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    weekday = now.weekday()

    if weekday >= 5:
        return False

    # 上午 09:30-11:30
    if (hour == 9 and minute >= 30) or (hour == 10) or (hour == 11 and minute <= 30):
        return True
    # 下午 13:00-15:00
    if hour >= 13 and hour < 15 or (hour == 15 and minute == 0):
        return True

    return False

def load_previous_state():
    """加载上次的异动状态"""
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"alerts": [], "prices": {}, "timestamp": None}

def save_state(alerts, prices):
    """保存当前状态"""
    try:
        state = {
            "alerts": sorted(alerts),
            "prices": prices,
            "timestamp": datetime.now().isoformat()
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to save state: {e}", file=sys.stderr)

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
    prices = {}

    # 判断时段
    us_period = get_us_market_period()
    ashare_trading = is_ashare_trading()

    for sym, info in WATCHLIST.items():
        quote = fetch_quote(sym)
        if not quote:
            report_lines.append(info["name"] + " (" + sym + "): 数据获取失败")
            continue
        curr = quote["current"]
        prev = quote["previous"]
        chg = (curr - prev) / prev * 100
        prices[sym] = {"current": curr, "change_pct": chg}
        
        line = info["name"] + ": " + str(round(curr, 2)) + " " + info["unit"] + " (" + (("+" if chg > 0 else "") + str(round(chg, 2))) + "%)"
        report_lines.append(line)

        if abs(chg) >= info["threshold"]:
            direction = "📈" if chg > 0 else "📉"
            alerts.append(direction + " " + info["name"] + ": " + str(round(curr, 2)) + " " + info["unit"] + " " + (("+" if chg > 0 else "") + str(round(chg, 2))) + "%")

    print("=== 市场行情 " + now.strftime("%Y-%m-%d %H:%M") + " ===")
    print("美股时段:", us_period, "| A股交易:", "是" if ashare_trading else "否")
    for line in report_lines:
        print("  " + line)

    # 加载上次状态
    prev_state = load_previous_state()
    prev_alerts = set(prev_state.get("alerts", []))
    curr_alerts = set(alerts)
    
    # 保存当前状态
    save_state(alerts, prices)

    # 决定是否发送
    should_send = False
    reason = ""
    
    if not alerts:
        print("\n✅ 所有品种波动在阈值内")
        return "HEARTBEAT_OK"
    
    # 变化检测
    new_alerts = curr_alerts - prev_alerts
    if new_alerts:
        should_send = True
        reason = f"新异动: {len(new_alerts)}个"
    elif curr_alerts != prev_alerts:
        # 异动清单有变化（方向改变或品种变化）
        should_send = True
        reason = "异动清单变化"
    elif us_period == 'regular':
        # 美股常规交易时段，即使相同异动也定期发送
        should_send = True
        reason = "美股交易时段常规更新"
    elif ashare_trading and new_alerts:
        # A股时段只有新异动才发送
        should_send = True
        reason = "A股时段重大异动"
    else:
        reason = "异动无变化，非美股常规时段"

    print(f"\n发送决策: {should_send} ({reason})")

    if not should_send:
        return "HEARTBEAT_OK"

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

if __name__ == "__main__":
    result = main()
    print("\n" + result)
