#!/usr/bin/env python3
"""US night report v2 based on us_data manager (A-share style structure)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import sys
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from us_data import USDataManager

US_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "AVGO", "NFLX",
    "BABA", "PDD", "NIO", "XPEV", "LI",
    "^DJI", "^GSPC", "^IXIC", "QQQ", "SPY", "IWM", "XLE", "GLD", "SLV",
]

NAMES = {
    "^DJI": "道琼斯", "^GSPC": "标普500", "^IXIC": "纳斯达克", "QQQ": "纳指ETF", "SPY": "标普ETF",
    "IWM": "罗素2000ETF", "XLE": "能源ETF", "GLD": "黄金ETF", "SLV": "白银ETF",
}


def cn_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def fmt_name(sym: str) -> str:
    return NAMES.get(sym, sym)


def fetch_volume_flow(symbols: list[str]) -> dict[str, tuple[float | None, str]]:
    out: dict[str, tuple[float | None, str]] = {}
    try:
        data = yf.download(
            tickers=" ".join(symbols), period="10d", interval="1d", progress=False, group_by="ticker", threads=True
        )
    except Exception:
        return {s: (None, "degraded") for s in symbols}

    is_multi = isinstance(data.columns, pd.MultiIndex)
    for s in symbols:
        try:
            frame = data[s] if is_multi else data
            vol = pd.to_numeric(frame.get("Volume"), errors="coerce").dropna()
            close = pd.to_numeric(frame.get("Close"), errors="coerce").dropna()
            if len(vol) < 6 or len(close) < 2:
                out[s] = (None, "degraded")
                continue
            v_last = float(vol.iloc[-1])
            v_ma5 = float(vol.iloc[-6:-1].mean())
            price_up = float(close.iloc[-1] - close.iloc[-2]) >= 0
            ratio = (v_last / v_ma5) if v_ma5 > 0 else 1.0
            flow_score = (ratio - 1.0) * (1 if price_up else -1)
            out[s] = (flow_score, "proxy")
        except Exception:
            out[s] = (None, "degraded")
    return out


def dir_tag(v: float | None) -> str:
    if v is None:
        return "中性(降级)"
    if v > 0.15:
        return "偏多"
    if v < -0.15:
        return "偏空"
    return "中性"


def build_report() -> str:
    now = cn_now()
    mgr = USDataManager()
    snap = mgr.get_snapshots(US_WATCHLIST)
    by = {r.symbol: r for r in snap.itertuples(index=False)}

    def pct(sym: str) -> float | None:
        r = by.get(sym)
        return None if r is None else (float(r.pct) if pd.notna(r.pct) else None)

    def last(sym: str) -> float | None:
        r = by.get(sym)
        return None if r is None else (float(r.last) if pd.notna(r.last) else None)

    movers = []
    for s in US_WATCHLIST:
        p = pct(s)
        if p is not None:
            movers.append((s, p))
    movers_sorted = sorted(movers, key=lambda x: x[1], reverse=True)

    core = ["AAPL", "NVDA", "TSLA", "BABA", "PDD", "NIO", "QQQ", "SPY", "XLE", "GLD", "SLV"]
    flow = fetch_volume_flow(core)

    ok_cnt = int((snap["status"] == "ok").sum()) if not snap.empty else 0
    total = len(US_WATCHLIST)

    lines: list[str] = []
    lines.append(f"🌙 **完整美股夜盘复盘 | {now:%Y-%m-%d}（{['周一','周二','周三','周四','周五','周六','周日'][now.weekday()]} {now:%H:%M}）**")
    lines.append("")
    lines.append("1) **大盘总览**")
    for idx in ["^DJI", "^GSPC", "^IXIC"]:
        l, p = last(idx), pct(idx)
        if l is None or p is None:
            lines.append(f"- {fmt_name(idx)}：数据缺失")
        else:
            lines.append(f"- {fmt_name(idx)}：{l:,.2f}（{p:+.2f}%）")
    lines.append(f"- 数据命中率：{ok_cnt}/{total}（source: us_data chain）")

    lines.append("")
    lines.append("2) **宏观/海外驱动（夜盘）**")
    lines.append("- 核心看点：美债利率、美元指数、AI龙头财报预期。")
    lines.append("- 若利率回落+科技走强：成长链继续占优；反之高位波动加大。")
    lines.append("- 能源与贵金属受地缘与通胀预期扰动，夜盘易放大波动。")

    lines.append("")
    lines.append("3) **板块轮动与风格**")
    top3 = movers_sorted[:3]
    btm3 = movers_sorted[-3:]
    if top3:
        lines.append("- 领涨Top3：" + " / ".join([f"{fmt_name(s)} {p:+.2f}%" for s, p in top3]))
    if btm3:
        lines.append("- 领跌Top3：" + " / ".join([f"{fmt_name(s)} {p:+.2f}%" for s, p in btm3]))
    lines.append("- 风格结论：科技成长与资源防守轮动，优先跟随强势+回踩确认。")

    lines.append("")
    lines.append("4) **重点池全展开**")
    for s in US_WATCHLIST:
        l, p = last(s), pct(s)
        if l is None or p is None:
            lines.append(f"- {fmt_name(s)}（{s}）：数据缺失/源异常")
        else:
            lines.append(f"- {fmt_name(s)}（{s}）：{l:,.2f}（{p:+.2f}%）")

    lines.append("")
    lines.append("5) **资金面（固定章节）**")
    lines.append("- 口径：美股暂用成交量×价格方向代理（proxy），后续接入更细资金源。")
    for s in core:
        v, tag = flow.get(s, (None, "degraded"))
        if v is None:
            lines.append(f"- {s}：资金方向 {dir_tag(v)}（{tag}）")
        else:
            lines.append(f"- {s}：资金方向 {dir_tag(v)}（proxy={v:+.2f}）")
    lines.append("- 北向资金：不适用于美股；替代看美债/美元/行业ETF量价。")

    lines.append("")
    lines.append("6) **基本面/估值层（FV）**")
    lines.append("- 美股个股：当前夜盘以快照与流动性为主，FV_real 在日线深度报告补充。")
    lines.append("- ETF/指数：FV_real 不直接适用，采用结构与风格因子跟踪。")

    lines.append("")
    lines.append("7) **综合结论 + 对明日A股影响**")
    lines.append("- 结论1：若纳指维持强势，A股科技成长（算力/应用）情绪偏多。")
    lines.append("- 结论2：若贵金属/能源继续上行，A股资源链有高开惯性但不宜追高。")
    lines.append("- 结论3：夜盘波动放大，次日更看开盘后30分钟量能确认。")
    lines.append("- 动作A：主线仓位分批，不追高；动作B：弱转强再加仓；动作C：跌破关键位先减仓。")

    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3750] + "\n...（已截断，保留核心结构）"
    return text


if __name__ == "__main__":
    print(build_report())
