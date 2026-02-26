"""Technical indicator calculations using pandas-ta."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class TechnicalSignal:
    """Result of technical analysis for a single stock."""
    score: float = 0.0
    signals: list[str] = field(default_factory=list)
    indicators: dict = field(default_factory=dict)


def compute_technical(df: pd.DataFrame) -> TechnicalSignal:
    """Compute technical indicators and generate score from daily K-line data.

    Expects columns: date, open, high, low, close, volume.
    Returns: TechnicalSignal with score (0-100), signal descriptions, raw indicators.
    """
    if df is None or len(df) < 20:
        return TechnicalSignal(score=50.0, signals=["数据不足,使用中性评分"])

    try:
        import pandas_ta as ta
    except ImportError:
        logger.warning("pandas-ta not installed, using basic calculations")
        return _compute_basic(df)

    result = TechnicalSignal()
    close = df["close"].astype(float)
    score = 50.0

    # MACD
    try:
        macd = ta.macd(close)
        if macd is not None and not macd.empty:
            macd_val = macd.iloc[-1].get("MACD_12_26_9", 0)
            macd_signal = macd.iloc[-1].get("MACDs_12_26_9", 0)
            macd_hist = macd.iloc[-1].get("MACDh_12_26_9", 0)
            result.indicators["macd"] = round(float(macd_val), 3)
            result.indicators["macd_signal"] = round(float(macd_signal), 3)

            if macd_hist > 0 and (len(macd) < 2 or macd.iloc[-2].get("MACDh_12_26_9", 0) <= 0):
                score += 6
                result.signals.append(f"MACD金叉+6")
            elif macd_hist < 0 and (len(macd) < 2 or macd.iloc[-2].get("MACDh_12_26_9", 0) >= 0):
                score -= 6
                result.signals.append(f"MACD死叉-6")
            elif macd_hist > 0:
                score += 2
                result.signals.append(f"MACD多头+2")
            elif macd_hist < 0:
                score -= 2
                result.signals.append(f"MACD空头-2")
    except Exception as e:
        logger.debug(f"MACD calculation error: {e}")

    # RSI
    try:
        rsi = ta.rsi(close, length=14)
        if rsi is not None and not rsi.empty:
            rsi_val = float(rsi.iloc[-1])
            result.indicators["rsi"] = round(rsi_val, 1)
            if rsi_val > 80:
                score -= 4
                result.signals.append(f"RSI={rsi_val:.0f}超买-4")
            elif rsi_val > 70:
                score -= 2
                result.signals.append(f"RSI={rsi_val:.0f}偏高-2")
            elif rsi_val < 20:
                score += 4
                result.signals.append(f"RSI={rsi_val:.0f}超卖+4")
            elif rsi_val < 30:
                score += 2
                result.signals.append(f"RSI={rsi_val:.0f}偏低+2")
            else:
                result.signals.append(f"RSI={rsi_val:.0f}中性")

            rsi6 = ta.rsi(close, length=6)
            if rsi6 is not None and not rsi6.empty:
                rsi6_val = float(rsi6.iloc[-1])
                result.indicators["rsi6"] = round(rsi6_val, 1)
                if rsi6_val > 85:
                    score -= 2
                    result.signals.append(f"RSI6={rsi6_val:.0f}短线极度超买-2")
                elif rsi6_val < 15:
                    score += 2
                    result.signals.append(f"RSI6={rsi6_val:.0f}短线极度超卖+2")
    except Exception as e:
        logger.debug(f"RSI calculation error: {e}")

    # KDJ
    try:
        stoch = ta.stoch(df["high"].astype(float), df["low"].astype(float), close)
        if stoch is not None and not stoch.empty:
            k = float(stoch.iloc[-1].get("STOCHk_14_3_3", 50))
            d = float(stoch.iloc[-1].get("STOCHd_14_3_3", 50))
            result.indicators["kdj_k"] = round(k, 1)
            result.indicators["kdj_d"] = round(d, 1)
            if k > d and len(stoch) >= 2:
                prev_k = float(stoch.iloc[-2].get("STOCHk_14_3_3", 50))
                prev_d = float(stoch.iloc[-2].get("STOCHd_14_3_3", 50))
                if prev_k <= prev_d:
                    if k > 80:
                        score -= 1
                        result.signals.append(f"KDJ高位金叉(K={k:.0f}>80,钝化)-1")
                    else:
                        score += 4
                        result.signals.append(f"KDJ金叉+4")
                else:
                    if k > 85:
                        result.signals.append(f"KDJ高位钝化(K={k:.0f})")
                    else:
                        score += 1
            elif k < d:
                if k < 20:
                    score += 2
                    result.signals.append(f"KDJ低位死叉(超卖区)+2")
                else:
                    score -= 2
                    result.signals.append(f"KDJ空头-2")
    except Exception as e:
        logger.debug(f"KDJ calculation error: {e}")

    # Moving averages alignment
    try:
        ma5 = close.rolling(5).mean().iloc[-1]
        ma10 = close.rolling(10).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else None
        current = float(close.iloc[-1])

        result.indicators["ma5"] = round(float(ma5), 2)
        result.indicators["ma20"] = round(float(ma20), 2)

        if current > ma5 > ma10 > ma20:
            score += 4
            result.signals.append("均线多头排列+4")
        elif current < ma5 < ma10 < ma20:
            score -= 4
            result.signals.append("均线空头排列-4")

        if current > ma20 and float(close.iloc[-2]) <= float(close.rolling(20).mean().iloc[-2]):
            score += 3
            result.signals.append("突破MA20+3")

        if ma60 is not None:
            result.indicators["ma60"] = round(float(ma60), 2)
            if current > ma60:
                score += 2
                result.signals.append("站上MA60+2")
            else:
                score -= 1
                result.signals.append("低于MA60-1")

        ma120 = close.rolling(120).mean().iloc[-1] if len(close) >= 120 else None
        if ma120 is not None:
            result.indicators["ma120"] = round(float(ma120), 2)
            if current > ma120:
                score += 1
                result.signals.append("站上MA120+1(中长期趋势向好)")
            else:
                score -= 1
                result.signals.append("低于MA120-1(中长期趋势偏弱)")
    except Exception as e:
        logger.debug(f"MA calculation error: {e}")

    # Bollinger Bands position
    try:
        bbands = ta.bbands(close, length=20)
        if bbands is not None and not bbands.empty:
            upper = float(bbands.iloc[-1].get("BBU_20_2.0", 0))
            lower = float(bbands.iloc[-1].get("BBL_20_2.0", 0))
            mid = float(bbands.iloc[-1].get("BBM_20_2.0", 0))
            current = float(close.iloc[-1])
            if upper > lower:
                bb_pos = (current - lower) / (upper - lower)
                result.indicators["bb_position"] = round(bb_pos, 2)
                if bb_pos > 0.95:
                    score -= 3
                    result.signals.append(f"布林上轨压力-3")
                elif bb_pos < 0.05:
                    score += 3
                    result.signals.append(f"布林下轨支撑+3")
    except Exception as e:
        logger.debug(f"Bollinger calculation error: {e}")

    result.score = max(0, min(100, score))
    return result


def _compute_basic(df: pd.DataFrame) -> TechnicalSignal:
    """Fallback: basic calculations without pandas-ta."""
    close = df["close"].astype(float)
    score = 50.0
    signals = []

    ma5 = close.rolling(5).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    current = float(close.iloc[-1])

    if current > ma5 > ma20:
        score += 5
        signals.append("均线多头+5")
    elif current < ma5 < ma20:
        score -= 5
        signals.append("均线空头-5")

    changes = close.pct_change().dropna()
    if len(changes) >= 14:
        gains = changes[changes > 0].rolling(14).mean().iloc[-1] if len(changes[changes > 0]) >= 14 else 0
        losses = abs(changes[changes < 0].rolling(14).mean().iloc[-1]) if len(changes[changes < 0]) >= 14 else 1
        rsi = 100 - 100 / (1 + gains / max(losses, 0.001)) if losses else 50
        if rsi > 70:
            score -= 3
            signals.append(f"RSI={rsi:.0f}偏高-3")
        elif rsi < 30:
            score += 3
            signals.append(f"RSI={rsi:.0f}偏低+3")

    return TechnicalSignal(score=max(0, min(100, score)), signals=signals)
