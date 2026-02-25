#!/usr/bin/env python3
"""US watchlist 10-min snapshot monitor (batch-first, A-share style)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json
import sys
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from us_data import USDataManager

WATCHLIST = [
    # 核心AI与科技
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "AVGO", "NFLX", "ARM", "PLTR", "SMCI", "SOXX",
    # 中概/新能源车链
    "BABA", "PDD", "NIO", "XPEV", "LI", "BYDDY",
    # 指数与风格
    "^DJI", "^GSPC", "^IXIC", "QQQ", "SPY", "IWM",
    # 能源与清洁能源
    "XLE", "XOP", "XOM", "CVX", "OXY", "TAN", "ICLN", "ENPH", "FSLR",
    # 航空航天/国防
    "BA", "RTX", "LMT", "NOC", "ITA",
    # 贵金属/工业金属/锂
    "GLD", "SLV", "GC=F", "SI=F", "HG=F", "ALI=F", "LIT", "CPER",
]

NAMES = {
    "^DJI": "道琼斯", "^GSPC": "标普500", "^IXIC": "纳斯达克", "QQQ": "纳指ETF", "SPY": "标普ETF",
    "IWM": "罗素2000ETF", "XLE": "能源ETF", "XOP": "油气勘探ETF", "XOM": "埃克森美孚", "CVX": "雪佛龙", "OXY": "西方石油",
    "GLD": "黄金ETF", "SLV": "白银ETF", "TAN": "光伏ETF", "ICLN": "清洁能源ETF", "ENPH": "Enphase", "FSLR": "First Solar",
    "GC=F": "黄金主连", "SI=F": "白银主连", "HG=F": "铜主连", "ALI=F": "铝主连",
    "LIT": "锂产业ETF", "CPER": "铜ETF",
    "ARM": "Arm", "PLTR": "Palantir", "SMCI": "超微电脑", "SOXX": "半导体ETF", "BYDDY": "比亚迪(ADR)",
    "BA": "波音", "RTX": "雷神", "LMT": "洛克希德马丁", "NOC": "诺斯罗普格鲁曼", "ITA": "航空航天国防ETF",
}

ALERT_THRESHOLD = {
    "index": 1.0,
    "stock": 2.0,
    "metal": 1.5,
}

METALS = {"GLD", "SLV", "GC=F", "SI=F", "HG=F", "ALI=F", "LIT", "CPER"}
INDEXES = {"^DJI", "^GSPC", "^IXIC", "QQQ", "SPY", "IWM"}

THEMES = {
    "AI": ["NVDA", "MSFT", "AMD", "AVGO", "ARM", "PLTR", "SMCI", "SOXX"],
    "航空航天": ["BA", "RTX", "LMT", "NOC", "ITA"],
    "能源": ["XLE", "XOP", "XOM", "CVX", "OXY", "ICLN", "TAN", "ENPH", "FSLR"],
    "金属": ["GLD", "SLV", "GC=F", "SI=F", "HG=F", "ALI=F", "CPER", "LIT"],
}

STATE_FILE = Path("/tmp/us_theme_state.json")


def cn_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def in_us_trading_hours() -> bool:
    """US regular session 09:30-16:00 America/New_York, Mon-Fri."""
    ny = datetime.now(ZoneInfo("America/New_York"))
    if ny.weekday() >= 5:
        return False
    hm = ny.hour * 60 + ny.minute
    return (9 * 60 + 30) <= hm <= (16 * 60)


def fmt_name(sym: str) -> str:
    return NAMES.get(sym, sym)


def threshold_for(sym: str) -> float:
    if sym in INDEXES:
        return ALERT_THRESHOLD["index"]
    if sym in METALS:
        return ALERT_THRESHOLD["metal"]
    return ALERT_THRESHOLD["stock"]


def _theme_strength(pct_getter) -> tuple[str, dict[str, str]]:
    out = []
    tags: dict[str, str] = {}
    for k, syms in THEMES.items():
        vals = [pct_getter(s) for s in syms]
        vals = [v for v in vals if v is not None]
        if not vals:
            out.append(f"{k}:NA")
            tags[k] = "NA"
            continue
        m = sum(vals) / len(vals)
        tag = "强" if m >= 1.2 else ("偏强" if m >= 0.4 else ("偏弱" if m <= -0.4 else "中性"))
        tags[k] = tag
        out.append(f"{k}:{tag}({m:+.2f}%)")
    return " | ".join(out), tags


def _load_prev_theme_tags() -> dict[str, str]:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_theme_tags(tags: dict[str, str]) -> None:
    try:
        STATE_FILE.write_text(json.dumps(tags, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _theme_rotation_alert(curr: dict[str, str], prev: dict[str, str]) -> str | None:
    # 仅提示关键切换：强<->偏弱
    changes = []
    for k, c in curr.items():
        p = prev.get(k)
        if not p or p == c:
            continue
        if (p in ("强", "偏强") and c in ("偏弱",)) or (p in ("偏弱",) and c in ("强", "偏强")):
            changes.append(f"{k}:{p}→{c}")
    if not changes:
        return None
    return "主题轮动告警：" + "；".join(changes)


def build() -> str:
    now = cn_now()
    if not in_us_trading_hours():
        return "HEARTBEAT_OK"

    mgr = USDataManager()
    snap = mgr.get_snapshots(WATCHLIST)
    if snap is None or snap.empty:
        return "HEARTBEAT_OK"

    by = {r.symbol: r for r in snap.itertuples(index=False)}

    def pct(sym: str) -> float | None:
        r = by.get(sym)
        return None if r is None else (float(r.pct) if pd.notna(r.pct) else None)

    def last(sym: str) -> float | None:
        r = by.get(sym)
        return None if r is None else (float(r.last) if pd.notna(r.last) else None)

    ok_cnt = int((snap["status"] == "ok").sum()) if "status" in snap.columns else len(snap)
    total = len(WATCHLIST)

    movers: list[tuple[float, str]] = []
    price_lines: list[str] = []
    for s in WATCHLIST:
        p = pct(s)
        l = last(s)
        if p is None or l is None:
            price_lines.append(f"• {fmt_name(s)}（{s}）: 数据缺失/源异常")
            continue
        price_lines.append(f"• {fmt_name(s)}（{s}）: {l:,.2f} ({p:+.2f}%)")
        if abs(p) >= threshold_for(s):
            movers.append((abs(p), f"• {fmt_name(s)}（{s}） {p:+.2f}%"))

    if not movers:
        return "HEARTBEAT_OK"

    movers_sorted = [x[1] for x in sorted(movers, key=lambda t: t[0], reverse=True)[:10]]

    focus_groups = {
        "AI": ["NVDA", "MSFT", "AMD", "AVGO", "ARM", "PLTR", "SMCI", "SOXX"],
        "航空航天": ["BA", "RTX", "LMT", "NOC", "ITA"],
        "能源/光伏": ["XLE", "XOP", "XOM", "CVX", "OXY", "TAN", "ICLN", "ENPH", "FSLR"],
        "金属/锂": ["GLD", "SLV", "GC=F", "SI=F", "HG=F", "ALI=F", "CPER", "LIT"],
    }

    # simple risk preference proxy from major indexes
    p_nas = pct("^IXIC") or 0.0
    p_spx = pct("^GSPC") or 0.0
    if p_nas > 0.8 and p_spx > 0.4:
        risk_line = "风险偏好回升（成长偏强）。"
    elif p_nas < -0.8 and p_spx < -0.4:
        risk_line = "风险偏好走弱（防守优先）。"
    else:
        risk_line = "风险偏好中性震荡。"

    theme_line, theme_tags = _theme_strength(pct)
    prev_tags = _load_prev_theme_tags()
    rotation_alert = _theme_rotation_alert(theme_tags, prev_tags)
    _save_theme_tags(theme_tags)

    lines = [
        f"⚡ **美股10分钟快照 | {now:%H:%M}**",
        "",
        "1) **风险偏好一句话**",
        f"- {risk_line}",
        f"- 主题强弱：{theme_line}",
        *([f"- ⚠️ {rotation_alert}"] if rotation_alert else []),
        "",
        "2) **异动清单（批量快照）**",
        *movers_sorted,
        "",
        "3) **关注池分组快照（混合版）**",
    ]

    for g, syms in focus_groups.items():
        vals = []
        for s in syms:
            p = pct(s)
            l = last(s)
            if p is None or l is None:
                vals.append(f"{fmt_name(s)} NA")
            else:
                vals.append(f"{fmt_name(s)} {p:+.2f}%")
        lines.append(f"- {g}: " + " | ".join(vals))

    lines.extend([
        "",
        "4) **关键驱动**",
        "- 驱动：AI算力/应用 + 航空航天/国防 + 能源/光伏 + 金属链（黄金/白银/铜/铝/锂）同步扫描触发。",
        "",
        "5) **对A股影响**",
        "- 若金属链继续走强，A股资源/有色可能受益；若纳指回落，成长波动加大。",
        "",
        "6) **风险与执行建议**",
        "- 先看开盘30分钟量能确认，不追高；分批执行，跌破关键位先减仓。",
        f"- 数据命中率：{ok_cnt}/{total}（source: us_data batch）",
    ])

    text = "\n".join(lines)
    return text[:1800]


if __name__ == "__main__":
    print(build())
