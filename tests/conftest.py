"""pytest 配置和共享 fixture."""

import sys
import os
import pytest
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "mcp-server"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "trading-quant" / "scripts"))


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环用于异步测试."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_quote_data():
    """示例行情数据 (QuoteData 对象)."""
    from data_sources.base import QuoteData
    
    return QuoteData(
        code="002202",
        name="金风科技",
        price=28.38,
        change_pct=4.11,
        open=28.0,
        high=28.99,
        low=27.88,
        pre_close=27.26,
        volume=195680500,
        amount=5573780000,
        volume_ratio=1.77,
        turnover_rate=5.59,
        pe=45.0,
        pb=3.11,
        market_cap=949.21,
        bid1=28.22,
        ask1=28.23,
    )


@pytest.fixture
def sample_kline_data():
    """示例 K 线数据 (DataFrame)."""
    import pandas as pd
    import numpy as np
    
    np.random.seed(42)
    dates = pd.date_range("2026-02-01", periods=60, freq="D")
    
    return pd.DataFrame({
        "open": 26 + np.random.randn(60).cumsum() * 0.5,
        "high": 27 + np.random.randn(60).cumsum() * 0.5,
        "low": 25 + np.random.randn(60).cumsum() * 0.5,
        "close": 26 + np.random.randn(60).cumsum() * 0.5,
        "volume": np.random.randint(1e8, 5e8, 60),
    }, index=dates)


@pytest.fixture
def sample_capital_flow_data():
    """示例资金流数据."""
    return {
        "code": "002202",
        "source": "ths",
        "total_amount": 55.73,  # 亿
        "data_points": 121,
        "main_force": {
            "main_net_inflow_wan": 34422.44,  # 万
            "super_big_net_wan": 2972.68,
            "big_net_wan": 31449.75,
            "signal": "主力流入",
            "source": "akshare_T+1",
        }
    }


@pytest.fixture
def mock_tencent_response():
    """Mock 腾讯行情响应."""
    return {
        "002202": {
            "code": "002202",
            "name": "金风科技",
            "price": 28.38,
            "change_pct": 4.11,
            "volume": 195680500,
            "amount": 5573780000,
            "volume_ratio": 1.77,
        }
    }


@pytest.fixture
def mock_eastmoney_main_flow():
    """Mock 东方财富主力资金响应."""
    return {
        "code": "002202",
        "main_net_inflow_wan": 34422.44,
        "super_big_net_wan": 2972.68,
        "big_net_wan": 31449.75,
        "signal": "主力流入",
    }


@pytest.fixture
def sample_news_sentiment():
    """示例新闻情绪数据."""
    return {
        "sentiment": "neutral",
        "score": 0.1,
        "bullish_count": 3,
        "bearish_count": 2,
        "news_count": 5,
    }
