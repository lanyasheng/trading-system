#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["akshare>=1.16", "pandas-ta>=0.3.14b"]
# ///
"""
A股技术分析工具

功能：
- K线数据获取与技术指标计算
- 买卖信号生成（EMA/RSI/MACD/布林带）
- 趋势判断和支撑阻力位

Usage:
    uv run tech_analyze.py 600519                # 单只分析
    uv run tech_analyze.py 600519 000858         # 多只分析
    uv run tech_analyze.py 600519 --period daily  # 日线分析
    uv run tech_analyze.py 600519 --signals       # 仅显示买卖信号
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta

FETCH_STATS = {
    "eastmoney_ok": 0,
    "eastmoney_fail": 0,
    "fallback_ok": 0,
    "fallback_fail": 0,
}


def _normalize_kline_df(df):
    """标准化不同源字段命名"""
    import pandas as pd

    df = df.rename(columns={
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
        "成交额": "amount", "振幅": "amplitude",
        "涨跌幅": "pct_change", "涨跌额": "change",
        "换手率": "turnover",
        "date": "date", "open": "open", "close": "close",
        "high": "high", "low": "low", "volume": "volume",
        "amount": "amount", "turnover": "turnover",
    })

    for col in ["open", "close", "high", "low", "volume", "amount", "turnover"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def fetch_kline_data(stock_code, period="daily", count=120):
    """获取 K 线数据（东财失败时自动降级）"""
    try:
        import akshare as ak

        if period == "daily":
            start_date = (datetime.now() - timedelta(days=count * 2)).strftime("%Y%m%d")
            end_date = datetime.now().strftime("%Y%m%d")
            hist_period = "daily"
        elif period == "weekly":
            start_date = (datetime.now() - timedelta(days=count * 10)).strftime("%Y%m%d")
            end_date = datetime.now().strftime("%Y%m%d")
            hist_period = "weekly"
        else:
            start_date = (datetime.now() - timedelta(days=count * 2)).strftime("%Y%m%d")
            end_date = datetime.now().strftime("%Y%m%d")
            hist_period = "daily"

        last_err = None
        for i in range(1, 4):
            try:
                df = ak.stock_zh_a_hist(
                    symbol=stock_code,
                    period=hist_period,
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq"
                )
                if df is not None and not df.empty:
                    FETCH_STATS["eastmoney_ok"] += 1
                    return _normalize_kline_df(df).tail(count), "eastmoney"
                raise ValueError("empty dataframe")
            except Exception as e:
                last_err = e
                FETCH_STATS["eastmoney_fail"] += 1
                print(
                    f"[warn] 东财K线失败({stock_code}) attempt={i}/3 error={e.__class__.__name__}: {e}",
                    file=sys.stderr,
                )
                if i < 3:
                    time.sleep(0.4 * i)

        # fallback: 尝试新浪日线（周线请求降级为日线）
        if hasattr(ak, "stock_zh_a_daily"):
            try:
                df_fb = ak.stock_zh_a_daily(symbol=stock_code, adjust="qfq")
                if df_fb is not None and not df_fb.empty:
                    FETCH_STATS["fallback_ok"] += 1
                    # 某些版本 date 在索引上
                    if "date" not in df_fb.columns and str(getattr(df_fb.index, "name", "")).lower() in {"date", "日期"}:
                        df_fb = df_fb.reset_index()
                    # 先标准化列名，再按起始日期过滤
                    df_fb = _normalize_kline_df(df_fb)
                    if "date" in df_fb.columns:
                        date_cut = datetime.strptime(start_date, "%Y%m%d").strftime("%Y-%m-%d")
                        df_fb = df_fb[df_fb["date"].astype(str) >= date_cut]
                    return df_fb.tail(count), "sina_fallback"
                raise ValueError("fallback empty dataframe")
            except Exception as fb_err:
                FETCH_STATS["fallback_fail"] += 1
                print(
                    f"[warn] 降级源失败({stock_code}) error={fb_err.__class__.__name__}: {fb_err}",
                    file=sys.stderr,
                )

        print(f"K线数据获取失败({stock_code}): {last_err}", file=sys.stderr)
        return None, "failed"
    except Exception as e:
        print(f"K线数据获取失败({stock_code}): {e}", file=sys.stderr)
        return None, "failed"


def calculate_indicators(df):
    """计算技术指标"""
    import pandas_ta as ta

    df.ta.ema(length=5, append=True)
    df.ta.ema(length=10, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=60, append=True)

    df.ta.rsi(length=14, append=True)

    df.ta.macd(fast=12, slow=26, signal=9, append=True)

    df.ta.bbands(length=20, std=2, append=True)

    df.ta.atr(length=14, append=True)

    df.ta.obv(append=True)

    try:
        df.ta.kdj(append=True)
    except Exception:
        df.ta.stoch(append=True)

    return df


def generate_signals(df, stock_code=""):
    """生成买卖信号"""
    signals = []
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    close = latest.get("close", 0)
    rsi = latest.get("RSI_14", 50)
    macd = latest.get("MACD_12_26_9", 0)
    macd_signal = latest.get("MACDs_12_26_9", 0)
    macd_hist = latest.get("MACDh_12_26_9", 0)
    ema5 = latest.get("EMA_5", close)
    ema10 = latest.get("EMA_10", close)
    ema20 = latest.get("EMA_20", close)
    ema60 = latest.get("EMA_60", close)
    bbl = latest.get("BBL_20_2.0", close * 0.95)
    bbu = latest.get("BBU_20_2.0", close * 1.05)

    prev_macd = prev.get("MACD_12_26_9", 0)
    prev_macd_signal = prev.get("MACDs_12_26_9", 0)

    buy_score = 0
    sell_score = 0
    reasons_buy = []
    reasons_sell = []

    # RSI 信号
    if rsi and rsi < 30:
        buy_score += 2
        reasons_buy.append(f"RSI 超卖({rsi:.1f})")
    elif rsi and rsi > 70:
        sell_score += 2
        reasons_sell.append(f"RSI 超买({rsi:.1f})")
    elif rsi and rsi < 40:
        buy_score += 1
        reasons_buy.append(f"RSI 偏低({rsi:.1f})")

    # MACD 金叉/死叉
    if macd and macd_signal:
        if prev_macd < prev_macd_signal and macd > macd_signal:
            buy_score += 3
            reasons_buy.append("MACD 金叉")
        elif prev_macd > prev_macd_signal and macd < macd_signal:
            sell_score += 3
            reasons_sell.append("MACD 死叉")

    # 均线排列
    if ema5 and ema10 and ema20:
        if ema5 > ema10 > ema20:
            buy_score += 2
            reasons_buy.append("均线多头排列")
        elif ema5 < ema10 < ema20:
            sell_score += 2
            reasons_sell.append("均线空头排列")

    # 布林带
    if close and bbl and bbu:
        if close <= bbl:
            buy_score += 2
            reasons_buy.append("触及布林下轨")
        elif close >= bbu:
            sell_score += 2
            reasons_sell.append("触及布林上轨")

    # 价格与60日均线
    if close and ema60:
        if close > ema60 * 1.02:
            buy_score += 1
            reasons_buy.append("站稳60日均线上方")
        elif close < ema60 * 0.98:
            sell_score += 1
            reasons_sell.append("跌破60日均线")

    # 综合判断
    if buy_score >= 5:
        signal = "STRONG_BUY"
        action = "强烈买入信号"
    elif buy_score >= 3:
        signal = "BUY"
        action = "买入信号"
    elif sell_score >= 5:
        signal = "STRONG_SELL"
        action = "强烈卖出信号"
    elif sell_score >= 3:
        signal = "SELL"
        action = "卖出信号"
    else:
        signal = "HOLD"
        action = "观望"

    return {
        "stock": stock_code,
        "signal": signal,
        "action": action,
        "buy_score": buy_score,
        "sell_score": sell_score,
        "reasons_buy": reasons_buy,
        "reasons_sell": reasons_sell,
        "price": float(close) if close else 0,
        "rsi": float(rsi) if rsi else 0,
        "macd_hist": float(macd_hist) if macd_hist else 0,
        "support": float(bbl) if bbl else 0,
        "resistance": float(bbu) if bbu else 0,
    }


def get_trend_description(df):
    """获取趋势描述"""
    if len(df) < 20:
        return "数据不足"

    close = df["close"].iloc[-1]
    close_5d = df["close"].iloc[-5]
    close_20d = df["close"].iloc[-20]

    chg_5d = (close - close_5d) / close_5d * 100
    chg_20d = (close - close_20d) / close_20d * 100

    ema20 = df.get("EMA_20")
    if ema20 is not None and len(ema20) >= 5:
        ema_slope = (ema20.iloc[-1] - ema20.iloc[-5]) / ema20.iloc[-5] * 100
    else:
        ema_slope = 0

    if chg_5d > 3 and chg_20d > 5:
        trend = "强势上涨"
    elif chg_5d > 1:
        trend = "温和上涨"
    elif chg_5d < -3 and chg_20d < -5:
        trend = "强势下跌"
    elif chg_5d < -1:
        trend = "温和下跌"
    else:
        trend = "横盘震荡"

    return f"{trend}（5日{chg_5d:+.1f}% 20日{chg_20d:+.1f}%）"


def analyze_stock(stock_code, period="daily"):
    """完整的单只股票技术分析"""
    print(f"\n分析 {stock_code}...", file=sys.stderr)
    df, data_source = fetch_kline_data(stock_code, period)
    if df is None or df.empty:
        return None

    df = calculate_indicators(df)
    signal = generate_signals(df, stock_code)
    trend = get_trend_description(df)

    latest = df.iloc[-1]
    result = {
        "stock": stock_code,
        "data_source": data_source,
        "date": str(latest.get("date", "")),
        "close": float(latest.get("close", 0)),
        "volume": int(latest.get("volume", 0)),
        "turnover": float(latest.get("turnover", 0)) if latest.get("turnover") else 0,
        "trend": trend,
        "signal": signal,
        "indicators": {
            "EMA5": round(float(latest.get("EMA_5", 0)), 2),
            "EMA10": round(float(latest.get("EMA_10", 0)), 2),
            "EMA20": round(float(latest.get("EMA_20", 0)), 2),
            "EMA60": round(float(latest.get("EMA_60", 0)), 2),
            "RSI": round(float(latest.get("RSI_14", 0)), 1),
            "MACD": round(float(latest.get("MACD_12_26_9", 0)), 4),
            "MACD_Signal": round(float(latest.get("MACDs_12_26_9", 0)), 4),
            "MACD_Hist": round(float(latest.get("MACDh_12_26_9", 0)), 4),
            "BB_Upper": round(float(latest.get("BBU_20_2.0", 0)), 2),
            "BB_Lower": round(float(latest.get("BBL_20_2.0", 0)), 2),
        }
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="A股技术分析")
    parser.add_argument("stocks", nargs="+", help="股票代码")
    parser.add_argument("--period", default="daily", choices=["daily", "weekly"])
    parser.add_argument("--signals", action="store_true", help="仅显示买卖信号")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    results = []
    for code in args.stocks:
        result = analyze_stock(code, args.period)
        if result:
            results.append(result)

    source_hits = {}
    for r in results:
        src = r.get("data_source", "unknown")
        source_hits[src] = source_hits.get(src, 0) + 1

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        print(
            json.dumps({
                "source_hits": source_hits,
                "fetch_stats": FETCH_STATS,
            }, ensure_ascii=False),
            file=sys.stderr,
        )
    else:
        for r in results:
            sig = r["signal"]
            signal_emoji = {
                "STRONG_BUY": "🟢🟢", "BUY": "🟢",
                "STRONG_SELL": "🔴🔴", "SELL": "🔴",
                "HOLD": "🟡"
            }.get(sig["signal"], "⚪")

            print(f"\n{'='*50}")
            print(f"📊 {r['stock']} | {r['date']} | ¥{r['close']}")
            print(f"🧭 数据源: {r.get('data_source', 'unknown')}")
            print(f"📈 趋势: {r['trend']}")
            print(f"{signal_emoji} 信号: **{sig['action']}** (买{sig['buy_score']}/卖{sig['sell_score']})")

            if sig["reasons_buy"]:
                print(f"  🟢 买入因素: {', '.join(sig['reasons_buy'])}")
            if sig["reasons_sell"]:
                print(f"  🔴 卖出因素: {', '.join(sig['reasons_sell'])}")

            print(f"  支撑位: ¥{sig['support']:.2f} | 阻力位: ¥{sig['resistance']:.2f}")

            if not args.signals:
                ind = r["indicators"]
                print(f"\n  技术指标:")
                print(f"  • EMA: 5日={ind['EMA5']} 10日={ind['EMA10']} 20日={ind['EMA20']} 60日={ind['EMA60']}")
                print(f"  • RSI(14): {ind['RSI']}")
                print(f"  • MACD: {ind['MACD']} Signal: {ind['MACD_Signal']} Hist: {ind['MACD_Hist']}")
                print(f"  • 布林带: 上轨={ind['BB_Upper']} 下轨={ind['BB_Lower']}")

        print(f"\n📌 数据源命中统计: {source_hits}")
        print(f"📌 抓取统计: {FETCH_STATS}", file=sys.stderr)


if __name__ == "__main__":
    main()
