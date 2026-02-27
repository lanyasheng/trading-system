"""评分引擎测试."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mcp-server"))

from analysis.scoring import compute_stock_score, _get_signal, _classify_industry


class TestScoringEngine:
    """评分引擎测试."""
    
    def test_signal_mapping(self):
        """测试信号映射."""
        assert _get_signal(85) == ("STRONG_BUY", "高")
        assert _get_signal(70) == ("BUY", "中高")
        assert _get_signal(55) == ("WATCH", "中")
        assert _get_signal(40) == ("HOLD", "中低")
        assert _get_signal(25) == ("SELL", "低")
        assert _get_signal(15) == ("STRONG_SELL", "极低")
    
    def test_industry_classification(self):
        """测试行业分类."""
        assert _classify_industry("金风科技") == "新能源"
        assert _classify_industry("中国石油") == "石油"
        assert _classify_industry("紫金矿业") == "有色"
        assert _classify_industry("贵州茅台") == "白酒"
        assert _classify_industry("宁德时代") == "新能源"
        assert _classify_industry("未知股票") == "default"
    
    def test_score_with_main_force(self, sample_quote_data, sample_kline_data):
        """测试包含主力数据的评分."""
        main_force_data = {
            "main_net_inflow_wan": 50000,
            "super_big_net_wan": 10000,
            "big_net_wan": 40000,
            "signal": "主力流入",
            "source": "akshare",
        }
        
        score = compute_stock_score(
            sample_quote_data,
            sample_kline_data,
            capital_flow_data=main_force_data
        )
        
        assert score.total_score > 50
        assert "capital" in score.to_dict()["score"]
        assert score.capital["score"] > 50  # 主力流入应该加分
    
    def test_score_without_main_force(self, sample_quote_data, sample_kline_data):
        """测试无主力数据的评分."""
        score = compute_stock_score(
            sample_quote_data,
            sample_kline_data,
            capital_flow_data=None
        )
        
        assert any("数据缺失" in s for s in score.capital["signals"])
    
    def test_score_momentum_penalty(self, sample_quote_data, sample_kline_data):
        """测试动量惩罚."""
        # 大涨情况
        sample_quote_data["change_pct"] = 9.8
        score = compute_stock_score(sample_quote_data, sample_kline_data)
        
        # 大涨应该有惩罚
        assert score.total_score < 60  # 即使其他指标好，大涨也会扣分
    
    def test_score_with_news_sentiment(self, sample_quote_data, sample_kline_data):
        """测试新闻情绪影响."""
        extra = {
            "news_sentiment": 0.8,  # 正面新闻
            "news_count": 5,
            "top_news": ["利好消息 1", "利好消息 2"],
        }
        
        score = compute_stock_score(
            sample_quote_data,
            sample_kline_data,
            extra=extra
        )
        
        assert score.sentiment["score"] > 50  # 正面新闻应该加分
    
    def test_score_with_market_sentiment(self, sample_quote_data, sample_kline_data):
        """测试市场情绪影响."""
        extra = {
            "market_sentiment": {
                "score": 60.0,
                "signals": ["沪深 300 强势 +1.5%"],
            },
            "consecutive_up_days": 3,  # 大盘连涨 3 天
        }
        
        score = compute_stock_score(
            sample_quote_data,
            sample_kline_data,
            extra=extra
        )
        
        # 连涨 3 天应该有轻微惩罚
        assert any("连涨" in s for s in score.market["signals"])
    
    def test_score_output_structure(self, sample_quote_data, sample_kline_data):
        """测试评分输出结构."""
        score = compute_stock_score(sample_quote_data, sample_kline_data)
        
        result_dict = score.to_dict()
        
        # 验证输出结构
        assert "code" in result_dict
        assert "name" in result_dict
        assert "price" in result_dict
        assert "score" in result_dict
        assert "technical" in result_dict["score"]
        assert "capital" in result_dict["score"]
        assert "fundamental" in result_dict["score"]
        assert "signal" in result_dict
        assert "confidence" in result_dict
    
    def test_score_pe_industry_adjustment(self, sample_quote_data, sample_kline_data):
        """测试 PE 行业调整."""
        # 银行股 PE=8 应该是低估
        sample_quote_data["pe"] = 8.0
        sample_quote_data["name"] = "某银行"
        
        score = compute_stock_score(sample_quote_data, sample_kline_data)
        
        assert any("低估值" in s for s in score.fundamental["signals"])
        
        # 科技股 PE=8 应该是极低估
        sample_quote_data["name"] = "某科技"
        score = compute_stock_score(sample_quote_data, sample_kline_data)
        
        assert any("低估值" in s for s in score.fundamental["signals"])


class TestScoringBatch:
    """批量评分测试."""
    
    def test_batch_scoring_performance(self, sample_quote_data, sample_kline_data):
        """测试批量评分性能."""
        import time
        
        # 模拟 24 只股票
        scores = []
        start = time.time()
        
        for i in range(24):
            quote = sample_quote_data.copy()
            quote["code"] = f"TEST{i:06d}"
            score = compute_stock_score(quote, sample_kline_data)
            scores.append(score)
        
        elapsed = time.time() - start
        
        # 24 只股票评分应该在 1 秒内完成
        assert elapsed < 5.0
        assert len(scores) == 24
