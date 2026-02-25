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
from scripts.report_templates import get_template

US_WATCHLIST = [
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

THEMES = {
    "AI": ["NVDA", "MSFT", "AMD", "AVGO", "ARM", "PLTR", "SMCI", "SOXX"],
    "航空航天": ["BA", "RTX", "LMT", "NOC", "ITA"],
    "能源": ["XLE", "XOP", "XOM", "CVX", "OXY", "ICLN", "TAN", "ENPH", "FSLR"],
    "金属": ["GLD", "SLV", "GC=F", "SI=F", "HG=F", "ALI=F", "CPER", "LIT"],
}

NAMES = {
    "^DJI": "道琼斯", "^GSPC": "标普500", "^IXIC": "纳斯达克", "QQQ": "纳指ETF", "SPY": "标普ETF",
    "IWM": "罗素2000ETF", "XLE": "能源ETF", "XOP": "油气勘探ETF", "XOM": "埃克森美孚", "CVX": "雪佛龙", "OXY": "西方石油",
    "GLD": "黄金ETF", "SLV": "白银ETF", "TAN": "光伏ETF", "ICLN": "清洁能源ETF", "ENPH": "Enphase", "FSLR": "First Solar",
    "GC=F": "黄金主连", "SI=F": "白银主连", "HG=F": "铜主连", "ALI=F": "铝主连", "LIT": "锂产业ETF", "CPER": "铜ETF",
    "ARM": "Arm", "PLTR": "Palantir", "SMCI": "超微电脑", "SOXX": "半导体ETF", "BYDDY": "比亚迪(ADR)",
    "BA": "波音", "RTX": "雷神", "LMT": "洛克希德马丁", "NOC": "诺斯罗普格鲁曼", "ITA": "航空航天国防ETF",
}


def cn_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def fmt_name(sym: str) -> str:
    return NAMES.get(sym, sym)


def confidence_tag(level: str) -> str:
    return {"high": "高", "medium": "中", "low": "低", "degraded": "降级"}.get(level, "中")


def fetch_capital_signal_multisource(symbols: list[str]) -> dict[str, dict]:
    """Multi-factor capital signal (proxy):
    - factor A: volume shock * direction
    - factor B: money-flow multiplier (MFM) * volume ratio

    Return per symbol:
    {score, direction_source, confidence, factors_ok}
    """
    out: dict[str, dict] = {}
    try:
        data = yf.download(
            tickers=" ".join(symbols), period="20d", interval="1d", progress=False, group_by="ticker", threads=True
        )
    except Exception:
        return {
            s: {"score": None, "direction_source": "yf_proxy_multifactor", "confidence": "degraded", "factors_ok": "0/2"}
            for s in symbols
        }

    is_multi = isinstance(data.columns, pd.MultiIndex)
    for s in symbols:
        try:
            frame = data[s] if is_multi else data
            vol = pd.to_numeric(frame.get("Volume"), errors="coerce").dropna()
            close = pd.to_numeric(frame.get("Close"), errors="coerce").dropna()
            high = pd.to_numeric(frame.get("High"), errors="coerce").dropna()
            low = pd.to_numeric(frame.get("Low"), errors="coerce").dropna()

            if len(vol) < 8 or len(close) < 3:
                out[s] = {
                    "score": None,
                    "direction_source": "yf_proxy_multifactor",
                    "confidence": "degraded",
                    "factors_ok": "0/2",
                }
                continue

            # factor A
            v_last = float(vol.iloc[-1])
            v_ma5 = float(vol.iloc[-6:-1].mean()) if len(vol) >= 6 else float(vol.mean())
            ret1 = float(close.iloc[-1] / close.iloc[-2] - 1.0)
            a = ((v_last / v_ma5) - 1.0) * (1 if ret1 >= 0 else -1) if v_ma5 > 0 else 0.0

            # factor B
            h = float(high.iloc[-1]) if len(high) else float(close.iloc[-1])
            l = float(low.iloc[-1]) if len(low) else float(close.iloc[-1])
            c = float(close.iloc[-1])
            denom = (h - l)
            mfm = (((c - l) - (h - c)) / denom) if denom != 0 else 0.0
            vol_ratio = (v_last / v_ma5) if v_ma5 > 0 else 1.0
            b = mfm * vol_ratio

            factors_ok = 2
            if denom == 0:
                factors_ok -= 1
            if v_ma5 <= 0:
                factors_ok -= 1

            score = 0.6 * a + 0.4 * b

            if len(vol) >= 15 and factors_ok == 2:
                conf = "high"
            elif len(vol) >= 10 and factors_ok >= 1:
                conf = "medium"
            else:
                conf = "low"

            out[s] = {
                "score": float(score),
                "direction_source": "yf_proxy_multifactor",
                "confidence": conf,
                "factors_ok": f"{factors_ok}/2",
            }
        except Exception:
            out[s] = {
                "score": None,
                "direction_source": "yf_proxy_multifactor",
                "confidence": "degraded",
                "factors_ok": "0/2",
            }
    return out


def dir_tag(v: float | None) -> str:
    if v is None:
        return "中性(降级)"
    if v > 0.15:
        return "偏多"
    if v < -0.15:
        return "偏空"
    return "中性"


def theme_strength(pct_getter) -> str:
    out = []
    for k, syms in THEMES.items():
        vals = [pct_getter(s) for s in syms]
        vals = [v for v in vals if v is not None]
        if not vals:
            out.append(f"{k}:NA")
            continue
        m = sum(vals) / len(vals)
        tag = "强" if m >= 1.2 else ("偏强" if m >= 0.4 else ("偏弱" if m <= -0.4 else "中性"))
        out.append(f"{k}:{tag}({m:+.2f}%)")
    return " | ".join(out)


def build_report() -> str:
    now = cn_now()
    mgr = USDataManager()
    snap = mgr.get_snapshots(US_WATCHLIST)
    by = {r.symbol: r for r in snap.itertuples(index=False)}
    template = get_template("us_night")

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

    core = [
        "AAPL", "NVDA", "TSLA", "ARM", "PLTR", "SOXX",  # AI
        "BABA", "PDD", "NIO", "BYDDY", "QQQ", "SPY",     # 中概/风格
        "XLE", "XOP", "XOM", "CVX", "TAN", "ICLN",       # 能源/光伏
        "ITA", "BA",                                          # 航空航天
        "GLD", "SLV", "GC=F", "SI=F", "HG=F", "ALI=F", "LIT", "CPER",  # 金属/锂
    ]
    flow = fetch_capital_signal_multisource(core)

    ok_cnt = int((snap["status"] == "ok").sum()) if not snap.empty else 0
    total = len(US_WATCHLIST)

    weekday = ['周一','周二','周三','周四','周五','周六','周日'][now.weekday()]
    lines: list[str] = []
    lines.append(template["title"].format(date=f"{now:%Y-%m-%d}", weekday=weekday, time=f"{now:%H:%M}"))
    lines.append("")

    sections = template["sections"]
    lines.append(sections[0])
    for idx in ["^DJI", "^GSPC", "^IXIC"]:
        l, p = last(idx), pct(idx)
        if l is None or p is None:
            lines.append(f"- {fmt_name(idx)}：数据缺失")
        else:
            lines.append(f"- {fmt_name(idx)}：{l:,.2f}（{p:+.2f}%）")
    lines.append(f"- 数据命中率：{ok_cnt}/{total}（source: us_data chain）")

    lines.append("")
    lines.append(sections[1])
    lines.append("- 核心看点：美债利率、美元指数、AI龙头财报预期。")
    lines.append("- 若利率回落+科技走强：成长链继续占优；反之高位波动加大。")
    lines.append("- 能源与贵金属受地缘与通胀预期扰动，夜盘易放大波动。")

    lines.append("")
    lines.append(sections[2])
    theme_line = theme_strength(pct)
    top3 = movers_sorted[:3]
    btm3 = movers_sorted[-3:]
    if top3:
        lines.append("- 领涨Top3：" + " / ".join([f"{fmt_name(s)} {p:+.2f}%" for s, p in top3]))
    if btm3:
        lines.append("- 领跌Top3：" + " / ".join([f"{fmt_name(s)} {p:+.2f}%" for s, p in btm3]))
    lines.append(f"- 主题强弱：{theme_line}")
    lines.append("- 风格结论：科技成长与资源防守轮动，优先跟随强势+回踩确认。")

    lines.append("")
    lines.append(sections[3])
    metals = ["GLD", "SLV", "GC=F", "SI=F", "HG=F", "ALI=F", "LIT", "CPER"]
    equities = [s for s in US_WATCHLIST if s not in metals]

    lines.append("- 股票/指数组：")
    for s in equities:
        l, p = last(s), pct(s)
        if l is None or p is None:
            lines.append(f"  - {fmt_name(s)}（{s}）：数据缺失/源异常")
        else:
            lines.append(f"  - {fmt_name(s)}（{s}）：{l:,.2f}（{p:+.2f}%）")

    lines.append("- 贵金属/工业金属组：")
    for s in metals:
        l, p = last(s), pct(s)
        if l is None or p is None:
            lines.append(f"  - {fmt_name(s)}（{s}）：数据缺失/源异常")
        else:
            lines.append(f"  - {fmt_name(s)}（{s}）：{l:,.2f}（{p:+.2f}%）")

    lines.append("")
    lines.append(sections[4])
    lines.append("- 口径：美股采用多因子代理资金（量价冲击+AD资金乘数）；并附源标记与置信度分层。")
    degrade_n = 0
    for s in core:
        item = flow.get(s, {"score": None, "direction_source": "yf_proxy_multifactor", "confidence": "degraded", "factors_ok": "0/2"})
        v = item["score"]
        source = item["direction_source"]
        conf = confidence_tag(item["confidence"])
        factors_ok = item["factors_ok"]
        if v is None:
            degrade_n += 1
            lines.append(f"- {s}：资金方向 {dir_tag(v)}｜源={source}｜置信度={conf}｜因子={factors_ok}")
        else:
            lines.append(f"- {s}：资金方向 {dir_tag(v)}（{v:+.2f}）｜源={source}｜置信度={conf}｜因子={factors_ok}")
    lines.append(f"- 资金口径健康度：{len(core)-degrade_n}/{len(core)}")
    lines.append("- 北向资金：不适用于美股；替代看美债/美元/行业ETF量价。")

    lines.append("")
    lines.append(sections[5])
    lines.append("- 美股个股：当前夜盘以快照与流动性为主，FV_real 在日线深度报告补充。")
    lines.append("- ETF/指数：FV_real 不直接适用，采用结构与风格因子跟踪。")

    lines.append("")
    lines.append(sections[6])
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
