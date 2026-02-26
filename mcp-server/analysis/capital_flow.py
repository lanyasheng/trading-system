"""Capital flow analysis — volume/turnover/bid-ask based scoring."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from data_sources.base import QuoteData

logger = logging.getLogger(__name__)


@dataclass
class CapitalSignal:
    """Capital flow analysis result."""
    score: float = 50.0
    signals: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def compute_capital(quote: QuoteData, avg_volume: float = 0, avg_amount: float = 0) -> CapitalSignal:
    """Compute capital flow score from real-time quote data.

    Uses volume ratio, turnover rate, bid-ask spread, and amount anomaly.
    avg_volume/avg_amount: 5-day average for comparison.
    """
    score = 50.0
    signals = []
    metrics = {}

    # Volume ratio (量比)
    vr = quote.volume_ratio
    if vr > 0:
        metrics["volume_ratio"] = round(vr, 2)
        if vr > 5:
            score += 8
            signals.append(f"量比{vr:.1f}极度放量+8")
        elif vr > 3:
            score += 5
            signals.append(f"量比{vr:.1f}显著放量+5")
        elif vr > 1.5:
            score += 2
            signals.append(f"量比{vr:.1f}温和放量+2")
        elif vr < 0.5:
            score -= 3
            signals.append(f"量比{vr:.1f}缩量-3")

    # Turnover rate (换手率)
    tr = quote.turnover_rate
    if tr > 0:
        metrics["turnover_rate"] = round(tr, 2)
        if tr > 15:
            score += 3
            signals.append(f"换手率{tr:.1f}%高度活跃+3")
        elif tr > 8:
            score += 1
            signals.append(f"换手率{tr:.1f}%活跃+1")
        elif tr < 1:
            score -= 2
            signals.append(f"换手率{tr:.1f}%低迷-2")

    # Amount comparison (成交额对比)
    if avg_amount > 0 and quote.amount > 0:
        amount_ratio = quote.amount / avg_amount
        metrics["amount_ratio"] = round(amount_ratio, 2)
        if amount_ratio > 3:
            score += 5
            signals.append(f"成交额{amount_ratio:.1f}倍均值+5")
        elif amount_ratio > 1.5:
            score += 2
            signals.append(f"成交额{amount_ratio:.1f}倍均值+2")
        elif amount_ratio < 0.5:
            score -= 2
            signals.append(f"成交额仅{amount_ratio:.1f}倍均值-2")

    # Bid-ask pressure (买卖压力)
    if quote.bid1 > 0 and quote.ask1 > 0:
        spread = (quote.ask1 - quote.bid1) / quote.bid1 * 100
        metrics["spread_pct"] = round(spread, 3)
        if spread < 0.05:
            score += 2
            signals.append("买卖价差极窄(流动性好)+2")

    # Price-volume divergence: price up but volume down => warning
    if quote.change_pct > 2 and vr > 0 and vr < 0.8:
        score -= 4
        signals.append(f"涨{quote.change_pct:.1f}%但缩量(量价背离)-4")
    elif quote.change_pct < -2 and vr > 3:
        score -= 3
        signals.append(f"跌{quote.change_pct:.1f}%且放量(资金出逃)-3")

    # 量比+方向修正: 放量上涨谨慎, 放量下跌警惕
    if quote.volume_ratio > 2:
        if quote.change_pct > 3:
            score -= 3
            signals.append(f"放量大涨(量比{quote.volume_ratio:.1f})-3(追高风险)")
        elif quote.change_pct < -3:
            score -= 5
            signals.append(f"放量大跌(量比{quote.volume_ratio:.1f})-5(出逃信号)")
        elif quote.change_pct > 1:
            signals.append(f"放量上涨(量比{quote.volume_ratio:.1f},温和)")
    
    return CapitalSignal(
        score=max(0, min(100, score)),
        signals=signals,
        metrics=metrics,
    )
