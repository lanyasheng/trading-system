"""资金流分析模块测试."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mcp-server"))

from analysis.capital_flow import compute_capital, CapitalSignal


class TestCapitalFlow:
    """资金流分析测试."""
    
    def test_volume_ratio_high(self, sample_quote_data):
        """测试高量比评分."""
        from data_sources.base import QuoteData
        quote = QuoteData(**{**vars(sample_quote_data), "volume_ratio": 5.5})
        result = compute_capital(quote)
        
        assert isinstance(result, CapitalSignal)
        assert result.score > 50  # 量比高应该加分
        assert any("极度放量" in s for s in result.signals)
    
    def test_volume_ratio_low(self, sample_quote_data):
        """测试低量比评分."""
        from data_sources.base import QuoteData
        quote = QuoteData(**{**vars(sample_quote_data), "volume_ratio": 0.3})
        result = compute_capital(quote)
        
        assert result.score < 50  # 量比低应该扣分
        assert any("缩量" in s for s in result.signals)
    
    def test_turnover_rate_high(self, sample_quote_data):
        """测试高换手率评分."""
        from data_sources.base import QuoteData
        quote = QuoteData(**{**vars(sample_quote_data), "turnover_rate": 16.0})
        result = compute_capital(quote)
        
        assert any("高度活跃" in s for s in result.signals)
    
    def test_turnover_rate_low(self, sample_quote_data):
        """测试低换手率评分."""
        from data_sources.base import QuoteData
        quote = QuoteData(**{**vars(sample_quote_data), "turnover_rate": 0.5})
        result = compute_capital(quote)
        
        assert any("低迷" in s for s in result.signals)
    
    def test_spread_narrow(self, sample_quote_data):
        """测试买卖价差窄评分."""
        # sample_quote_data 已经有窄价差
        result = compute_capital(sample_quote_data)
        
        assert any("流动性好" in s for s in result.signals)
    
    def test_main_force_inflow(self, sample_quote_data):
        """测试主力净流入评分."""
        main_force_data = {
            "main_net_inflow_wan": 50000,  # 5 亿
            "super_big_net_wan": 10000,
            "big_net_wan": 40000,
            "signal": "主力流入",
            "source": "akshare",
        }
        result = compute_capital(sample_quote_data, main_force_data=main_force_data)
        
        assert result.score > 55  # 主力大幅流入应该加分
        assert any("主力大幅流入" in s for s in result.signals)
        assert "akshare" in str(result.signals)  # 标注数据源
    
    def test_main_force_outflow(self, sample_quote_data):
        """测试主力净流出评分."""
        main_force_data = {
            "main_net_inflow_wan": -50000,  # -5 亿
            "super_big_net_wan": -30000,
            "big_net_wan": -20000,
            "signal": "主力流出",
            "source": "akshare",
        }
        result = compute_capital(sample_quote_data, main_force_data=main_force_data)
        
        assert result.score < 45  # 主力大幅流出应该扣分
        assert any("主力大幅流出" in s for s in result.signals)
    
    def test_main_force_missing(self, sample_quote_data):
        """测试主力数据缺失."""
        result = compute_capital(sample_quote_data, main_force_data=None)
        
        # 主力数据缺失时，评分应该在 50 分左右 (中性)
        assert 45 <= result.score <= 55
        # 信号数量应该正常
        assert len(result.signals) >= 2
    
    def test_price_volume_divergence_up(self, sample_quote_data):
        """测试量价背离 (上涨缩量)."""
        from data_sources.base import QuoteData
        quote = QuoteData(**{**vars(sample_quote_data), "change_pct": 5.0, "volume_ratio": 0.5})
        result = compute_capital(quote)
        
        assert any("量价背离" in s for s in result.signals)
    
    def test_price_volume_divergence_down(self, sample_quote_data):
        """测试量价背离 (下跌放量)."""
        from data_sources.base import QuoteData
        quote = QuoteData(**{**vars(sample_quote_data), "change_pct": -5.0, "volume_ratio": 4.0})
        result = compute_capital(quote)
        
        assert any("资金出逃" in s for s in result.signals)
    
    def test_momentum_penalty_high_gain(self, sample_quote_data):
        """测试动量惩罚 (大涨)."""
        from data_sources.base import QuoteData
        quote = QuoteData(**{**vars(sample_quote_data), "change_pct": 9.8, "volume_ratio": 3.5})
        result = compute_capital(quote)
        
        assert any("追高风险" in s for s in result.signals)
    
    def test_score_bounds(self, sample_quote_data):
        """测试评分边界 (0-100)."""
        from data_sources.base import QuoteData
        # 极端情况：所有正面信号
        quote = QuoteData(**{**vars(sample_quote_data), "volume_ratio": 6.0, "turnover_rate": 20.0})
        result = compute_capital(quote)
        assert 0 <= result.score <= 100
    
    def test_metrics_output(self, sample_quote_data):
        """测试指标输出."""
        result = compute_capital(sample_quote_data)
        
        assert "volume_ratio" in result.metrics
        assert "turnover_rate" in result.metrics
        assert result.metrics["volume_ratio"] == sample_quote_data.volume_ratio
        assert result.metrics["turnover_rate"] == sample_quote_data.turnover_rate


class TestCapitalFlowBatch:
    """批量资金流测试."""
    
    @pytest.mark.asyncio
    async def test_batch_call(self):
        """测试批量调用."""
        from data_sources.capital_flow_manager import CapitalFlowManager
        
        mgr = CapitalFlowManager()
        codes = ["002202", "601857", "512400"]
        
        results = await mgr.get_capital_flows_batch(codes)
        
        assert len(results) == 3
        for code in codes:
            assert code in results
            assert "source" in results[code]
        
        await mgr.close()
    
    @pytest.mark.asyncio
    async def test_batch_partial_failure(self):
        """测试批量调用部分失败."""
        from data_sources.capital_flow_manager import CapitalFlowManager
        
        mgr = CapitalFlowManager()
        codes = ["002202", "INVALID", "601857"]
        
        results = await mgr.get_capital_flows_batch(codes)
        
        # 即使部分失败，也应该返回所有代码的结果
        assert len(results) == 3
        assert "INVALID" in results
        assert results["INVALID"]["source"] == "missing"
        
        await mgr.close()
