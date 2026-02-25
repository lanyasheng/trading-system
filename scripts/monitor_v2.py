#!/usr/bin/env python3
"""Integration step 1: watchlist monitor with lightweight TradingScore."""

from __future__ import annotations

import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stock_data import StockDataManager
from stock_data.utils import normalize_code

WATCHLIST = [
    "002202", "601857", "601899", "000426",
    "515790", "020274", "515210", "518880", "159840",
    # 主流趋势观测ETF（非优先评分）
    "510300", "510500", "159915", "588000", "512400", "512660", "512880", "561560",
]
PRIORITY = [
    "002202", "020274", "515210", "515790", "601857", "601899", "518880", "159840",
    "510300", "510500", "159915", "588000", "512400", "512660", "512880", "561560",
]
HISTORY_DAYS = 540
MIN_SCORE_BARS = 120

NAME_MAP = {
    "600519": "贵州茅台",
    "000858": "五粮液",
    "002594": "比亚迪",
    "002202": "金风科技",
    "601899": "紫金矿业",
    "000426": "兴业银锡",
    "601857": "中国石油",
    "159840": "锂电池ETF",
    "515790": "光伏ETF",
    "020274": "细分化工产业指数",
    "515210": "钢铁ETF",
    "518880": "黄金ETF",
    "510300": "沪深300ETF",
    "510500": "中证500ETF",
    "159915": "创业板ETF",
    "588000": "科创50ETF",
    "512400": "有色ETF",
    "512660": "航天军工ETF",
    "512880": "证券ETF",
    "561560": "电力ETF",
}

# 事件层上下文（由当前运行中的分钟动量构建，不依赖外部网络）
EVENT_CONTEXT: dict[str, float] = {}


def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def is_etf(code: str) -> bool:
    return str(code).startswith(("15", "16", "51", "56", "58"))


def fetch_real_fundamental(code: str) -> dict:
    base = {
        "status": "no_data",
        "pe": math.nan,
        "pb": math.nan,
        "roe": math.nan,
        "revenue_yoy": math.nan,
        "profit_yoy": math.nan,
        "operating_cashflow": math.nan,
    }
    if is_etf(code):
        base["status"] = "etf"
        return base
    try:
        import akshare as ak  # type: ignore
    except Exception:
        return base

    def _flatten(obj) -> dict[str, float]:
        out: dict[str, float] = {}
        try:
            df = obj if isinstance(obj, pd.DataFrame) else pd.DataFrame(obj)
            if df is None or df.empty:
                return out
            if {"item", "value"}.issubset(set(df.columns)):
                for _, r in df.iterrows():
                    out[str(r.get("item", ""))] = pd.to_numeric(r.get("value"), errors="coerce")
            elif len(df.columns) >= 2 and df.shape[1] == 2:
                for _, r in df.iterrows():
                    out[str(r.iloc[0])] = pd.to_numeric(r.iloc[1], errors="coerce")
            else:
                last = df.tail(1).iloc[0]
                for k, v in last.items():
                    out[str(k)] = pd.to_numeric(v, errors="coerce")
        except Exception:
            return out
        return out

    def _call_fund_func(fn_name: str):
        f = getattr(ak, fn_name, None)
        if f is None:
            return None
        # 按常见参数名逐一尝试，优先同花顺/新浪接口
        trials = [
            {"symbol": code}, {"stock": code}, {"code": code}, {"ticker": code},
            {"symbol": f"sh{code}"}, {"symbol": f"sz{code}"},
            {"stock": f"sh{code}"}, {"stock": f"sz{code}"},
        ]
        for kw in trials:
            try:
                return f(**kw)
            except Exception:
                continue
        try:
            return f(code)
        except Exception:
            return None

    merged: dict[str, float] = {}
    ok = 0
    # 优先级：同花顺/新浪 > 其余 > 东财
    source_priority = [
        "stock_financial_abstract_ths",
        "stock_financial_benefit_ths",
        "stock_financial_cash_ths",
        "stock_financial_debt_ths",
        "stock_financial_report_sina",
        "stock_financial_analysis_indicator",
        "stock_individual_info_em",
        "stock_financial_analysis_indicator_em",
    ]
    for fn in source_priority:
        try:
            obj = _call_fund_func(fn)
            flat = _flatten(obj)
            if flat:
                merged.update(flat)
                ok += 1
        except Exception:
            continue

    alias = {
        "pe": ["pe", "市盈率", "市盈率ttm", "pe_ttm"],
        "pb": ["pb", "市净率", "pb_mrq"],
        "roe": ["roe", "净资产收益率", "roe(摊薄)", "加权净资产收益率"],
        "revenue_yoy": ["营业收入同比增长", "营收同比", "revenue_yoy"],
        "profit_yoy": ["净利润同比增长", "净利润同比", "profit_yoy", "扣非净利润同比增长"],
        "operating_cashflow": ["每股经营性现金流", "经营活动产生的现金流量净额", "经营现金流", "operating_cashflow"],
    }

    def _pick(keys: list[str]) -> float:
        for k, v in merged.items():
            lk = k.lower().replace(" ", "")
            for key in keys:
                kk = key.lower().replace(" ", "")
                if kk in lk and pd.notna(v):
                    return float(v)
        return math.nan

    res = dict(base)
    for k, ks in alias.items():
        res[k] = _pick(ks)
    got = sum(pd.notna(res[k]) for k in ("pe", "pb", "roe", "revenue_yoy", "profit_yoy", "operating_cashflow"))
    res["status"] = "normal" if got >= 3 else ("degraded" if got >= 1 else "no_data")
    if ok == 0 and got == 0:
        res["status"] = "no_data"
    return res


def _rsi14(close: pd.Series) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(14, min_periods=14).mean()
    avg_loss = loss.rolling(14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, math.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    hist = dif - dea
    return dif, dea, hist


def calc_trading_score(daily_df: pd.DataFrame) -> dict:
    need_cols = {"close"}
    if daily_df is None or daily_df.empty or not need_cols.issubset(set(daily_df.columns)):
        return {"status": "不可计算", "buy": 0, "sell": 0, "parts": ["数据不足"]}

    df = daily_df.copy().sort_values("date").reset_index(drop=True)
    df["close"] = _to_num(df["close"])
    df = df.dropna(subset=["close"])
    if len(df) < 20:
        return {"status": "降级计算", "buy": 0, "sell": 0, "parts": ["K线长度不足"]}

    close = df["close"]
    rsi = _rsi14(close)
    macd, macd_sig, _ = _macd(close)
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    std20 = close.rolling(20).std()
    bbu = ma20 + 2 * std20
    bbl = ma20 - 2 * std20

    cur = len(df) - 1
    prev = max(0, cur - 1)

    buy = 0
    sell = 0
    parts: list[str] = []
    status = "正常"

    rsi_now = rsi.iloc[cur]
    if pd.notna(rsi_now):
        if rsi_now < 30:
            buy += 2
            parts.append(f"RSI<{30}(+2)")
        elif rsi_now > 70:
            sell += 2
            parts.append(f"RSI>{70}(S+2)")
    else:
        status = "降级计算"
        parts.append("RSI缺失")

    if pd.notna(macd.iloc[cur]) and pd.notna(macd_sig.iloc[cur]) and pd.notna(macd.iloc[prev]) and pd.notna(macd_sig.iloc[prev]):
        if macd.iloc[prev] < macd_sig.iloc[prev] and macd.iloc[cur] > macd_sig.iloc[cur]:
            buy += 3
            parts.append("MACD金叉(+3)")
        elif macd.iloc[prev] > macd_sig.iloc[prev] and macd.iloc[cur] < macd_sig.iloc[cur]:
            sell += 3
            parts.append("MACD死叉(S+3)")
    else:
        status = "降级计算"
        parts.append("MACD缺失")

    if pd.notna(ma20.iloc[cur]) and pd.notna(ma60.iloc[cur]):
        if ma20.iloc[cur] > ma60.iloc[cur]:
            buy += 2
            parts.append("MA20>MA60(+2)")
        elif ma20.iloc[cur] < ma60.iloc[cur]:
            sell += 2
            parts.append("MA20<MA60(S+2)")
    else:
        status = "降级计算"
        parts.append("MA20/60缺失")

    if pd.notna(bbu.iloc[cur]) and pd.notna(bbl.iloc[cur]):
        c = close.iloc[cur]
        if c <= bbl.iloc[cur]:
            buy += 2
            parts.append("触下轨(+2)")
        elif c >= bbu.iloc[cur]:
            sell += 2
            parts.append("触上轨(S+2)")
    else:
        status = "降级计算"
        parts.append("BOLL缺失")

    if pd.notna(ma60.iloc[cur]):
        c = close.iloc[cur]
        if c > ma60.iloc[cur]:
            buy += 1
            parts.append("站上MA60(+1)")
        else:
            sell += 1
            parts.append("下破MA60(S+1)")
    else:
        status = "降级计算"
        parts.append("MA60缺失")

    return {"status": status, "buy": buy, "sell": sell, "parts": parts}


def safe_pct(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "NA"
    d = df.sort_values("date")
    c = _to_num(d["close"])
    if len(c) < 2 or pd.isna(c.iloc[-1]) or pd.isna(c.iloc[-2]) or c.iloc[-2] == 0:
        return "NA"
    pct = (c.iloc[-1] / c.iloc[-2] - 1) * 100
    return f"{pct:+.2f}%"


def load_daily_for_score(mgr: StockDataManager, code: str, end_s: str) -> tuple[pd.DataFrame, str]:
    """Cache-first long-window loader for stable scoring.

    先尝试 qfq；若不足则尝试不复权（ETF 常见）。
    """
    code_n = normalize_code(code)
    start_long = (date.today() - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")

    def _cached(adjust: str) -> pd.DataFrame:
        return mgr.cache.get(code=code_n, frequency="daily", adjust=adjust, start=start_long, end=end_s)

    c_qfq = _cached("qfq")
    c_raw = _cached("")
    cached_best = c_qfq if len(c_qfq) >= len(c_raw) else c_raw
    if len(cached_best) >= MIN_SCORE_BARS:
        return cached_best, "正常"

    # 增量更新：先 qfq，后不复权
    for adj in ("qfq", ""):
        try:
            mgr.get_daily(code=code_n, start=start_long, end=end_s, adjust=adj, use_cache=False)
        except Exception:
            pass

    c_qfq = _cached("qfq")
    c_raw = _cached("")
    refreshed_best = c_qfq if len(c_qfq) >= len(c_raw) else c_raw

    if len(refreshed_best) >= MIN_SCORE_BARS:
        return refreshed_best, "增量更新"
    if not refreshed_best.empty:
        return refreshed_best, "降级缓存"
    if not cached_best.empty:
        return cached_best, "降级缓存"
    return pd.DataFrame(), "不可计算"


def calc_capital_flow_score(minute_df: pd.DataFrame) -> dict:
    """Minute-based flow proxy score for intraday confirmation."""
    base = {
        "status": "降级计算",
        "flow": 0,
        "polarity": "neutral",
        "parts": ["分钟数据不足"],
    }
    if minute_df is None or minute_df.empty:
        return base

    try:
        df = minute_df.copy()
        if "close" not in df.columns:
            return base

        df["close"] = _to_num(df["close"])
        if "volume" in df.columns:
            df["volume"] = _to_num(df["volume"])
        elif "vol" in df.columns:
            df["volume"] = _to_num(df["vol"])
        else:
            df["volume"] = math.nan

        if "date" in df.columns:
            df = df.sort_values("date").reset_index(drop=True)
        else:
            df = df.reset_index(drop=True)

        df = df.dropna(subset=["close"])
        if len(df) < 12:
            return base

        flow = 0
        parts: list[str] = []

        # 因子1: 最新5m涨跌（以前一收盘代理=首根5m close）
        c_now = df["close"].iloc[-1]
        c_proxy_prev = df["close"].iloc[0]
        if pd.notna(c_now) and pd.notna(c_proxy_prev) and c_proxy_prev != 0:
            r = c_now / c_proxy_prev - 1
            if r > 0:
                flow += 1
                parts.append("5m涨跌(+1)")
            else:
                flow -= 1
                parts.append("5m涨跌(-1)")
        else:
            parts.append("5m涨跌缺失")

        # 因子2: 量能突变（最后1根对比近20根均量）
        if "volume" in df.columns and df["volume"].notna().any():
            vol = df["volume"]
            last_v = vol.iloc[-1]
            avg20 = vol.iloc[-20:].mean() if len(vol) >= 20 else vol.mean()
            if pd.notna(last_v) and pd.notna(avg20) and avg20 > 0:
                ratio = last_v / avg20
                if ratio >= 1.8:
                    flow += 1
                    parts.append("量能>=1.8x(+1)")
                elif ratio <= 0.6:
                    flow -= 1
                    parts.append("量能<=0.6x(-1)")
            else:
                parts.append("量能缺失")
        else:
            parts.append("量能缺失")

        # 因子3: 12根趋势斜率
        c12 = df["close"].iloc[-12:]
        if len(c12) == 12 and c12.notna().all():
            slope = (c12.iloc[-1] - c12.iloc[0]) / 11.0
            if slope > 0:
                flow += 1
                parts.append("12bar斜率(+1)")
            else:
                flow -= 1
                parts.append("12bar斜率(-1)")
        else:
            parts.append("趋势缺失")

        polarity = "positive" if flow > 0 else ("negative" if flow < 0 else "neutral")
        status = "正常" if len(parts) > 0 else "降级计算"
        return {"status": status, "flow": flow, "polarity": polarity, "parts": parts}
    except Exception:
        return base


def calc_batch_flow_from_snapshot(code: str, batch_rt: dict[str, dict[str, float]], daily_df: pd.DataFrame) -> dict:
    """Batch-first flow proxy in [-3,+3] using realtime snapshot + daily history."""
    base = {"status": "degraded", "flow": 0, "polarity": "neutral", "parts": ["snapshot_missing"], "code": code}
    try:
        score = 0
        ok = 0
        parts: list[str] = []
        rt = batch_rt.get(code, {})

        # 1) pct sign from batch snapshot
        pct = pd.to_numeric(rt.get("pct", math.nan), errors="coerce")
        if pd.notna(pct):
            s = 1 if float(pct) > 0 else -1
            score += s
            ok += 1
            parts.append(f"pct:{s:+d}")
        else:
            parts.append("pct:na")

        # 2) amount acceleration vs 20d avg from daily
        prev_close = math.nan
        if daily_df is not None and not daily_df.empty:
            d = daily_df.copy()
            if "date" in d.columns:
                d = d.sort_values("date")
            if "amount" in d.columns:
                amt = _to_num(d["amount"]).dropna()
                if len(amt) >= 6:
                    last_amt = float(amt.iloc[-1])
                    avg20 = float(amt.iloc[-20:].mean()) if len(amt) >= 20 else float(amt.mean())
                    if avg20 > 0:
                        ratio = last_amt / avg20
                        s = 1 if ratio >= 1.2 else (-1 if ratio <= 0.8 else 0)
                        score += s
                        ok += 1
                        parts.append(f"ta:{s:+d}")
                    else:
                        parts.append("ta:na")
                else:
                    parts.append("ta:na")
            else:
                parts.append("ta:na")

            # 3) close position vs prev close
            if "close" in d.columns:
                close_s = _to_num(d["close"]).dropna()
                if len(close_s) >= 1:
                    prev_close = float(close_s.iloc[-1])
        else:
            parts.extend(["ta:na"])

        close_now = pd.to_numeric(rt.get("close", math.nan), errors="coerce")
        if pd.notna(close_now) and pd.notna(prev_close) and float(prev_close) != 0:
            s = 1 if float(close_now) > float(prev_close) else (-1 if float(close_now) < float(prev_close) else 0)
            score += s
            ok += 1
            parts.append(f"cp:{s:+d}")
        else:
            parts.append("cp:na")

        flow = max(-3, min(3, int(score)))
        polarity = "positive" if flow > 0 else ("negative" if flow < 0 else "neutral")
        return {"status": "normal" if ok == 3 else "degraded", "flow": flow, "polarity": polarity, "parts": parts, "code": code}
    except Exception:
        return base


def calc_standard_flow_score(code: str, minute_df: pd.DataFrame, daily_df: pd.DataFrame) -> dict:
    """Standard flow layer in [-3,+3] using only local minute/daily proxies."""
    base = {"status": "degraded", "score": 0, "parts": ["flow_proxies_missing"], "code": code}
    try:
        score = 0
        ok = 0
        parts: list[str] = []

        # a) money-flow proxy: sum((close-open)*volume) on last 20 minute bars
        if minute_df is not None and not minute_df.empty and "close" in minute_df.columns:
            m = minute_df.copy()
            if "date" in m.columns:
                m = m.sort_values("date")
            m["close"] = _to_num(m["close"])
            m["open"] = _to_num(m["open"]) if "open" in m.columns else m["close"].shift(1)
            if "volume" in m.columns:
                m["volume"] = _to_num(m["volume"])
            elif "vol" in m.columns:
                m["volume"] = _to_num(m["vol"])
            else:
                m["volume"] = math.nan
            t = m[["close", "open", "volume"]].dropna().tail(20)
            if len(t) >= 8:
                mf = float(((t["close"] - t["open"]) * t["volume"]).sum())
                s = 1 if mf > 0 else (-1 if mf < 0 else 0)
                score += s
                ok += 1
                parts.append(f"mf20:{s:+d}")
            else:
                parts.append("mf20:na")
        else:
            parts.append("mf20:na")

        # b) large-bar pressure proxy on last 60 bars: top-decile volume up/down balance
        if minute_df is not None and not minute_df.empty and "close" in minute_df.columns:
            m = minute_df.copy()
            if "date" in m.columns:
                m = m.sort_values("date")
            m["close"] = _to_num(m["close"])
            m["open"] = _to_num(m["open"]) if "open" in m.columns else m["close"].shift(1)
            if "volume" in m.columns:
                m["volume"] = _to_num(m["volume"])
            elif "vol" in m.columns:
                m["volume"] = _to_num(m["vol"])
            else:
                m["volume"] = math.nan
            t = m[["close", "open", "volume"]].dropna().tail(60)
            if len(t) >= 20:
                q = t["volume"].quantile(0.9)
                big = t[t["volume"] >= q]
                up = int((big["close"] > big["open"]).sum())
                dn = int((big["close"] < big["open"]).sum())
                bal = up - dn
                s = 1 if bal >= 2 else (-1 if bal <= -2 else 0)
                score += s
                ok += 1
                parts.append(f"lbp:{s:+d}")
            else:
                parts.append("lbp:na")
        else:
            parts.append("lbp:na")

        # c) turnover acceleration proxy: last amount vs 20d avg amount
        if daily_df is not None and not daily_df.empty:
            d = daily_df.copy()
            if "date" in d.columns:
                d = d.sort_values("date")
            if "amount" in d.columns:
                amt = _to_num(d["amount"]).dropna()
            else:
                amt = pd.Series(dtype=float)
            if len(amt) >= 6:
                last = float(amt.iloc[-1])
                avg20 = float(amt.iloc[-20:].mean()) if len(amt) >= 20 else float(amt.mean())
                if avg20 > 0:
                    ratio = last / avg20
                    s = 1 if ratio >= 1.2 else (-1 if ratio <= 0.8 else 0)
                    score += s
                    ok += 1
                    parts.append(f"ta:{s:+d}")
                else:
                    parts.append("ta:na")
            else:
                parts.append("ta:na")
        else:
            parts.append("ta:na")

        # When minute proxies are missing, keep only daily amount term and degrade explicitly.
        score = max(-3, min(3, int(score)))
        minute_missing = ("mf20:na" in parts and "lbp:na" in parts)
        status = "degraded" if (ok < 3 or minute_missing) else "normal"
        if minute_missing and "minute_missing" not in parts:
            parts.append("minute_missing")
        return {"status": status, "score": score, "parts": parts, "code": code}
    except Exception:
        return base


def calc_fv_proxy_score(code: str, daily_df: pd.DataFrame) -> dict:
    """Fundamental/valuation fallback layer in [-3,+3] from price-position & trend quality."""
    base = {"status": "degraded", "score": 0, "parts": ["fv_proxies_missing"], "code": code}
    try:
        if daily_df is None or daily_df.empty or "close" not in daily_df.columns:
            return base
        d = daily_df.copy()
        if "date" in d.columns:
            d = d.sort_values("date")
        d["close"] = _to_num(d["close"])
        d = d.dropna(subset=["close"])
        if len(d) < 60:
            return base

        score = 0
        ok = 0
        parts: list[str] = []
        close = d["close"]

        # a) price percentile in 240d range: high=-1, mid=0, low=+1
        w = close.iloc[-240:] if len(close) >= 240 else close
        lo, hi, cur = float(w.min()), float(w.max()), float(w.iloc[-1])
        if hi > lo:
            pct = (cur - lo) / (hi - lo)
            s = 1 if pct <= 0.25 else (-1 if pct >= 0.75 else 0)
            score += s
            ok += 1
            parts.append(f"pp240:{s:+d}")
        else:
            parts.append("pp240:na")

        # b) earnings-quality fallback: return vol + drawdown stability
        ret = close.pct_change()
        vol60 = float(ret.iloc[-60:].std()) if len(ret.dropna()) >= 20 else math.nan
        roll_max = close.rolling(120, min_periods=20).max()
        dd = close / roll_max.replace(0, math.nan) - 1
        dd_cur = float(dd.iloc[-1]) if len(dd) else math.nan
        if pd.notna(vol60) and pd.notna(dd_cur):
            if vol60 <= 0.018 and dd_cur >= -0.08:
                s = 1
            elif vol60 >= 0.04 or dd_cur <= -0.2:
                s = -1
            else:
                s = 0
            score += s
            ok += 1
            parts.append(f"eq:{s:+d}")
        else:
            parts.append("eq:na")

        # c) long trend quality from MA60 slope
        ma60 = close.rolling(60, min_periods=40).mean()
        if len(ma60.dropna()) >= 20:
            m = ma60.dropna()
            slope = float(m.iloc[-1] / m.iloc[-20] - 1) if m.iloc[-20] != 0 else 0.0
            s = 1 if slope >= 0.02 else (-1 if slope <= -0.02 else 0)
            score += s
            ok += 1
            parts.append(f"ma60:{s:+d}")
        else:
            parts.append("ma60:na")

        score = max(-3, min(3, int(score)))
        return {"status": "normal" if ok == 3 else "degraded", "score": score, "parts": parts, "code": code}
    except Exception:
        return base


def calc_real_fv_score(code: str) -> dict:
    base = {"status": "no_data", "score": 0, "fields": {}}
    if is_etf(code):
        return {"status": "etf", "score": 0, "fields": {}}
    try:
        f = fetch_real_fundamental(code)
        s = 0
        used = 0
        pe = f.get("pe", math.nan)
        pb = f.get("pb", math.nan)
        roe = f.get("roe", math.nan)
        ry = f.get("revenue_yoy", math.nan)
        py = f.get("profit_yoy", math.nan)
        ocf = f.get("operating_cashflow", math.nan)

        if pd.notna(pe):
            s += 1 if pe <= 15 else (-1 if pe >= 40 else 0)
            used += 1
        if pd.notna(pb):
            s += 1 if pb <= 1.8 else (-1 if pb >= 5 else 0)
            used += 1
        if pd.notna(roe):
            s += 1 if roe >= 12 else (-1 if roe <= 5 else 0)
            used += 1
        if pd.notna(ry):
            s += 1 if ry > 0 else -1
            used += 1
        if pd.notna(py):
            s += 1 if py > 0 else -1
            used += 1
        if pd.notna(ocf):
            s += 1 if ocf > 0 else -1
            used += 1

        status = "normal" if used >= 4 else ("degraded" if used >= 1 else "no_data")
        return {"status": status, "score": max(-3, min(3, int(s))), "fields": f}
    except Exception:
        return base


def calc_risk_score(daily_df: pd.DataFrame) -> dict:
    """Risk layer score in [-2, +2]. Higher means lower risk support."""
    base = {"status": "降级计算", "score": 0, "parts": ["日线不足"]}
    try:
        need_cols = {"close"}
        if daily_df is None or daily_df.empty or not need_cols.issubset(set(daily_df.columns)):
            return base

        df = daily_df.copy().sort_values("date").reset_index(drop=True)
        for c in ("high", "low", "close"):
            if c in df.columns:
                df[c] = _to_num(df[c])
        if "high" not in df.columns:
            df["high"] = _to_num(df["close"])
        if "low" not in df.columns:
            df["low"] = _to_num(df["close"])
        df = df.dropna(subset=["close"])
        if len(df) < 25:
            return base

        close = df["close"]
        high = df["high"].fillna(close)
        low = df["low"].fillna(close)
        prev_close = close.shift(1)

        tr = pd.concat(
            [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr14 = tr.rolling(14, min_periods=10).mean()
        atr_ratio = atr14 / close.replace(0, math.nan)
        vol20 = close.pct_change().rolling(20, min_periods=15).std()
        hh20 = high.rolling(20, min_periods=10).max()
        dd20 = close / hh20.replace(0, math.nan) - 1

        cur_atr = atr_ratio.iloc[-1]
        cur_vol = vol20.iloc[-1]
        cur_dd = dd20.iloc[-1]
        if pd.isna(cur_atr) or pd.isna(cur_vol) or pd.isna(cur_dd):
            return {"status": "降级计算", "score": 0, "parts": ["风险因子缺失"]}

        score = 0
        parts: list[str] = []

        # ATR越低越稳定，给予正分；极高波动给负分
        if cur_atr <= 0.02:
            score += 1
            parts.append("ATR低(+1)")
        elif cur_atr >= 0.05:
            score -= 1
            parts.append("ATR高(-1)")

        # 20日收益波动率
        if cur_vol <= 0.02:
            score += 1
            parts.append("波动低(+1)")
        elif cur_vol >= 0.04:
            score -= 1
            parts.append("波动高(-1)")

        # 相对20日高点回撤
        if cur_dd >= -0.03:
            score += 1
            parts.append("回撤小(+1)")
        elif cur_dd <= -0.10:
            score -= 1
            parts.append("回撤大(-1)")

        score = max(-2, min(2, int(score)))
        return {"status": "正常", "score": score, "parts": parts}
    except Exception:
        return base


def calc_event_score(symbol: str) -> dict:
    """Event layer score from local cross-asset minute momentum context."""
    base = {"status": "降级计算", "score": 0, "parts": ["事件上下文不足"]}
    try:
        if not EVENT_CONTEXT:
            return base

        # 使用当前脚本可得的跨资产近似代理：
        # 黄金链: 黄金ETF(518880) + 紫金矿业(601899)
        # 能源链: 中国石油(601857) + 细分化工产业指数(020274)
        # 工业金属/周期: 钢铁ETF(515210) + 紫金矿业(601899)
        gold_m = EVENT_CONTEXT.get("518880", 0.0)
        miner_m = EVENT_CONTEXT.get("601899", 0.0)
        energy_m = EVENT_CONTEXT.get("601857", 0.0)
        chem_m = EVENT_CONTEXT.get("020274", 0.0)
        steel_m = EVENT_CONTEXT.get("515210", 0.0)

        theme_momentum: dict[str, float] = {
            "metals": (gold_m + miner_m + steel_m) / 3.0,
            "energy": (energy_m + chem_m) / 2.0,
            "new_energy": (EVENT_CONTEXT.get("515790", 0.0) + EVENT_CONTEXT.get("159840", 0.0)) / 2.0,
        }

        symbol_theme = {
            "518880": "metals",
            "601899": "metals",
            "515210": "metals",
            "000426": "metals",
            "601857": "energy",
            "020274": "energy",
            "515790": "new_energy",
            "159840": "new_energy",
            "002202": "new_energy",
        }
        theme = symbol_theme.get(symbol)
        if theme is None:
            return {"status": "正常", "score": 0, "parts": ["无主题映射"]}

        m = theme_momentum.get(theme, 0.0)
        if m > 0.005:
            return {"status": "正常", "score": 1, "parts": [f"{theme}动量正(+1)"]}
        if m < -0.005:
            return {"status": "正常", "score": -1, "parts": [f"{theme}动量负(-1)"]}
        return {"status": "正常", "score": 0, "parts": [f"{theme}动量中性"]}
    except Exception:
        return base


def total_score(
    tech_buy: int,
    tech_sell: int,
    flow_score: int,
    risk_score: int,
    event_score: int,
    sf_score: int,
    fv_score: int,
) -> int:
    return (tech_buy - tech_sell) + flow_score + risk_score + event_score + sf_score + fv_score


def overall_bias(
    tech_buy: int,
    tech_sell: int,
    flow_score: int,
    risk_score: int,
    event_score: int,
    sf_score: int,
    fv_score: int,
) -> str:
    total = total_score(tech_buy, tech_sell, flow_score, risk_score, event_score, sf_score, fv_score)
    if total > 0:
        return "偏多"
    if total < 0:
        return "偏空"
    return "中性"


def action_suggestion(total: int) -> str:
    if total >= 4:
        return "持有偏多"
    if total >= 1:
        return "持有观察"
    if total <= -3:
        return "减仓防守"
    return "观望"


def render_with_limit(
    end_s: str,
    price_lines: list[str],
    mover_lines: list[str],
    score_lines: list[str],
    src_line: str,
    limit: int = 1600,
) -> str:
    """Trim lower-priority lines first to keep output readable within limit."""
    keep_price = min(len(price_lines), 12)
    keep_movers = min(len(mover_lines), 6)
    keep_source = True

    def _pack() -> str:
        lines = [
            f"📊 MonitorV2 {end_s}",
            "价格摘要",
            *price_lines[:keep_price],
            "异动(|pct|>=1%)",
            *mover_lines[:keep_movers],
            "优先标的评分(技术+资金+SF+FV+风险+事件)",
            *score_lines,
        ]
        if keep_source:
            lines.append(f"源链路 {src_line}")
        return "\n".join(lines)

    text = _pack()
    if len(text) <= limit:
        return text

    for n in [10, 8, 6, 4]:
        keep_price = min(len(price_lines), n)
        text = _pack()
        if len(text) <= limit:
            return text

    for n in [4, 3, 2, 1]:
        keep_movers = min(len(mover_lines), n)
        text = _pack()
        if len(text) <= limit:
            return text

    keep_source = False
    text = _pack()
    if len(text) <= limit:
        return text

    return text[: max(0, limit - 4)] + " ..."


def fetch_batch_realtime_snapshot(codes: list[str]) -> dict[str, dict[str, float]]:
    """Batch fetch realtime quotes with Sina HQ API (header-enabled).

    Returns: {code: {"close": float, "pct": float}}
    """
    out: dict[str, dict[str, float]] = {}
    try:
        import requests  # type: ignore

        # Sina codes: sh600000 / sz000001
        symbols = []
        for c in codes:
            c = str(c).zfill(6)
            market = "sh" if c.startswith(("5", "6", "9")) else "sz"
            symbols.append(f"{market}{c}")

        url = "https://hq.sinajs.cn/list=" + ",".join(symbols)
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200 or not resp.text:
            return out

        # line example:
        # var hq_str_sz002202="金风科技,26.200,26.080,27.250,...,2026-02-25,13:43:21,00";
        for line in resp.text.splitlines():
            if "hq_str_" not in line or "=\"" not in line:
                continue
            try:
                left, right = line.split('="', 1)
                payload = right.rsplit('"', 1)[0]
                symbol = left.split("hq_str_")[-1].strip()
                code = symbol[-6:]
                parts = payload.split(",")
                # sina: [name, open, prev_close, close, high, low, ...]
                if len(parts) < 4:
                    continue
                prev_close = pd.to_numeric(parts[2], errors="coerce")
                close = pd.to_numeric(parts[3], errors="coerce")
                if pd.isna(close):
                    continue
                pct = math.nan
                if pd.notna(prev_close) and float(prev_close) != 0:
                    pct = (float(close) / float(prev_close) - 1.0) * 100.0
                out[code] = {"close": float(close), "pct": float(pct) if pd.notna(pct) else math.nan}
            except Exception:
                continue
    except Exception:
        return out
    return out


def fetch_northbound_multisource() -> dict:
    """Fetch northbound capital flow from multiple sources and mark anomaly.

    Returns: {status: normal|anomaly|unavailable, value: float|None, detail: str}
    """
    vals = []
    detail = []
    try:
        import akshare as ak  # type: ignore

        # Source A: minute northbound
        try:
            df = ak.stock_hsgt_fund_min_em()
            if df is not None and not df.empty and "北向资金" in df.columns:
                v = pd.to_numeric(df["北向资金"].iloc[-1], errors="coerce")
                if pd.notna(v):
                    vals.append(float(v))
                    detail.append(f"min:{float(v):.2f}")
        except Exception:
            pass

        # Source B: summary northbound (deep connect)
        try:
            df = ak.stock_hsgt_fund_flow_summary_em()
            if df is not None and not df.empty and {"板块", "成交净买额"}.issubset(df.columns):
                sub = df[df["板块"].astype(str).str.contains("深股通|沪股通", regex=True, na=False)]
                v = pd.to_numeric(sub["成交净买额"], errors="coerce").sum()
                if pd.notna(v):
                    vals.append(float(v))
                    detail.append(f"sum:{float(v):.2f}")
        except Exception:
            pass
    except Exception:
        pass

    if not vals:
        return {"status": "unavailable", "value": None, "detail": "无可用源"}

    # If most sources are 0 around close, treat as anomaly to avoid false signal.
    zero_cnt = sum(abs(v) < 1e-9 for v in vals)
    if zero_cnt >= max(1, len(vals) - 0):
        return {"status": "anomaly", "value": 0.0, "detail": "多源为0（口径异常）"}

    return {"status": "normal", "value": float(sum(vals) / len(vals)), "detail": ";".join(detail)}


def build() -> str:
    global EVENT_CONTEXT
    mgr = StockDataManager()
    end = date.today()
    start = end - timedelta(days=220)
    start_s = start.strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")

    daily_map: dict[str, pd.DataFrame] = {}
    minute_map: dict[str, pd.DataFrame] = {}
    fail_daily: set[str] = set()
    fail_min: set[str] = set()

    # 批量快照优先：一次拉全标的，减少逐条请求被限流风险
    batch_rt = fetch_batch_realtime_snapshot(WATCHLIST)

    for code in WATCHLIST:
        try:
            daily_map[code] = mgr.get_daily(code=code, start=start_s, end=end_s, use_cache=True)
        except Exception:
            daily_map[code] = pd.DataFrame()
            fail_daily.add(code)

        # 批量优先：不再逐标的拉取分钟线，避免限流抖动
        minute_map[code] = pd.DataFrame()

    price_lines = []
    movers = []
    for code in WATCHLIST:
        d = daily_map.get(code, pd.DataFrame())
        m = minute_map.get(code, pd.DataFrame())

        # 实时价优先：批量快照 -> 分钟线最后一根
        last_close = None
        prev_close = None
        pct_override = None

        rt = batch_rt.get(code)
        if rt is not None:
            last_close = rt.get("close")
            if pd.notna(rt.get("pct", math.nan)):
                pct_override = float(rt.get("pct"))

        if (last_close is None) and m is not None and not m.empty and "close" in m.columns:
            mc = _to_num(m.sort_values("date")["close"])
            if len(mc) > 0 and pd.notna(mc.iloc[-1]):
                last_close = float(mc.iloc[-1])

        if d is not None and not d.empty and "close" in d.columns:
            dc = _to_num(d.sort_values("date")["close"])
            if len(dc) > 0 and pd.notna(dc.iloc[-1]):
                prev_close = float(dc.iloc[-1])
            if last_close is None and len(dc) > 0 and pd.notna(dc.iloc[-1]):
                last_close = float(dc.iloc[-1])

        close_s = f"{last_close:.2f}" if last_close is not None else "NA"
        if pct_override is not None:
            pct_s = f"{pct_override:+.2f}%"
        elif last_close is not None and prev_close is not None and prev_close != 0:
            pct_s = f"{(last_close / prev_close - 1) * 100:+.2f}%"
        else:
            pct_s = "NA"

        note = ""
        if code in fail_daily and code in fail_min:
            note = " 不可计算"
        elif code in fail_daily or code in fail_min:
            note = " 降级计算"
        name = NAME_MAP.get(code, code)
        price_lines.append(f"• {code} {name} {close_s} {pct_s}{note}")
        if pct_s != "NA":
            v = float(pct_s.replace("%", ""))
            if abs(v) >= 1:
                movers.append((abs(v), f"• {code} {NAME_MAP.get(code, code)} {pct_s}"))

    # 事件层分钟动量上下文：使用分钟首尾close变化率
    EVENT_CONTEXT = {}
    for code in WATCHLIST:
        m = minute_map.get(code, pd.DataFrame())
        if m is None or m.empty or "close" not in m.columns:
            continue
        try:
            m2 = m.sort_values("date") if "date" in m.columns else m
            cc = _to_num(m2["close"]).dropna()
            if len(cc) >= 2 and cc.iloc[0] != 0:
                EVENT_CONTEXT[code] = float(cc.iloc[-1] / cc.iloc[0] - 1)
        except Exception:
            continue

    score_lines = []
    for code in PRIORITY:
        tech_score_df, _ = load_daily_for_score(mgr, code, end_s)
        tech = calc_trading_score(tech_score_df)
        minute_df = minute_map.get(code, pd.DataFrame())
        flow = calc_batch_flow_from_snapshot(code, batch_rt, tech_score_df)
        sf = calc_standard_flow_score(code, minute_df, tech_score_df)
        fv_real = calc_real_fv_score(code)
        fv_proxy = calc_fv_proxy_score(code, tech_score_df)
        risk = calc_risk_score(tech_score_df)
        event = calc_event_score(code)

        flow_score = 0 if flow["status"] == "降级计算" else int(flow.get("flow", 0))
        sf_score = int(sf.get("score", 0)) if sf.get("status") != "degraded" or "score" in sf else 0
        if is_etf(code):
            fv_score = int(fv_proxy.get("score", 0))
        else:
            fv_score = int(fv_real.get("score", 0)) if fv_real.get("status") in ("normal", "degraded") else int(fv_proxy.get("score", 0))
        risk_score = 0 if risk["status"] == "降级计算" else int(risk.get("score", 0))
        event_score = 0 if event["status"] == "降级计算" else int(event.get("score", 0))

        tscore = total_score(tech['buy'], tech['sell'], flow_score, risk_score, event_score, sf_score, fv_score)
        bias = overall_bias(tech['buy'], tech['sell'], flow_score, risk_score, event_score, sf_score, fv_score)
        act = action_suggestion(tscore)

        if is_etf(code):
            fv_txt = f"FV_real N/A(ETF) FV_proxy{int(fv_proxy.get('score', 0))}"
        else:
            fv_txt = f"FV_real{int(fv_real.get('score', 0))}({fv_real.get('status','no_data')})"
            if fv_real.get("status") != "normal":
                fv_txt += f" FV_proxy{int(fv_proxy.get('score', 0))}"

        if flow["status"] == "降级计算":
            score_lines.append(
                f"• {code} {NAME_MAP.get(code, code)} 技术B{tech['buy']}/S{tech['sell']} 资金F0(降级) 资金流SF{sf_score}({sf.get('status','degraded')}) {fv_txt} 风险R{risk_score} 事件E{event_score} => {bias}/{act}"
            )
        else:
            score_lines.append(
                f"• {code} {NAME_MAP.get(code, code)} 技术B{tech['buy']}/S{tech['sell']} 资金F{flow_score}({flow['polarity']}) 资金流SF{sf_score}({sf.get('status','degraded')}) {fv_txt} 风险R{risk_score} 事件E{event_score} => {bias}/{act}"
            )

    health = mgr.health_report()
    chain = health.get("chain", {})
    src_parts = []
    for src in ["sina", "baostock", "pytdx", "eastmoney"]:
        s = chain.get(src)
        if s:
            src_parts.append(f"{src} {s.get('success', 0)}/{s.get('fail', 0)}")
    src_line = " | ".join(src_parts) if src_parts else "暂无调用"
    # 链路口径修正：显示本轮批量快照是否命中
    src_line = f"snapshot:sina_batch {len(batch_rt)}/{len(WATCHLIST)} | " + src_line

    nb = fetch_northbound_multisource()
    if nb.get("status") == "normal":
        src_line += f" | 北向:{nb.get('value', 0.0):.2f}"
    elif nb.get("status") == "anomaly":
        src_line += " | 北向:异常(多源为0)"
    else:
        src_line += " | 北向:不可用"

    mover_lines = [x[1] for x in sorted(movers, key=lambda t: t[0], reverse=True)[:6]]
    if not mover_lines:
        mover_lines = ["• 无"]

    # 无分钟线时，实时时间戳使用系统时间近似本轮快照时间
    latest_ts = date.today().strftime("%Y-%m-%d") + " " + __import__('datetime').datetime.now().strftime("%H:%M:%S")
    src_line = f"{src_line} | 实时到:{latest_ts}"

    return render_with_limit(
        end_s=end_s,
        price_lines=price_lines,
        mover_lines=mover_lines,
        score_lines=score_lines,
        src_line=src_line,
        limit=1800,
    )


def main() -> None:
    try:
        print(build())
    except Exception as exc:
        print(f"📊 MonitorV2\n系统异常，已降级: {exc}")


if __name__ == "__main__":
    main()
