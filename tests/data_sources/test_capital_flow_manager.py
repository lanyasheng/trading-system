"""资本流管理器测试."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mcp-server"))


class TestCapitalFlowManager:
    """资本流管理器测试."""
    
    @pytest.mark.asyncio
    async def test_single_call_ths(self):
        """测试单只股票调用 (同花顺)."""
        from data_sources.capital_flow_manager import CapitalFlowManager
        
        mgr = CapitalFlowManager()
        result = await mgr.get_capital_flow("002202")
        
        assert "code" in result
        assert result["code"] == "002202"
        assert "source" in result
        assert result["source"] in ["ths", "em", "tencent", "akshare", "unknown"]
        
        await mgr.close()
    
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
    async def test_batch_with_invalid_code(self):
        """测试批量调用包含无效代码."""
        from data_sources.capital_flow_manager import CapitalFlowManager
        
        mgr = CapitalFlowManager()
        codes = ["002202", "INVALID", "601857"]
        
        results = await mgr.get_capital_flows_batch(codes)
        
        # 即使部分失败，也应该返回所有代码的结果
        assert len(results) == 3
        assert "INVALID" in results
        assert results["INVALID"]["source"] == "missing"
        
        await mgr.close()
    
    @pytest.mark.asyncio
    async def test_retry_mechanism(self):
        """测试重试机制."""
        from data_sources.capital_flow_manager import CapitalFlowManager
        
        mgr = CapitalFlowManager()
        
        # Mock 一个会失败的函数
        call_count = 0
        
        async def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("临时错误")
            return {"success": True}
        
        result = await mgr._retry_request(failing_func, max_retries=2, base_delay=0.1)
        
        # 应该重试后成功
        assert call_count == 2
        assert result == {"success": True}
        
        await mgr.close()
    
    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """测试重试耗尽."""
        from data_sources.capital_flow_manager import CapitalFlowManager
        
        mgr = CapitalFlowManager()
        
        # Mock 一个永远失败的函数
        async def always_failing():
            raise Exception("永久错误")
        
        result = await mgr._retry_request(always_failing, max_retries=2, base_delay=0.1)
        
        # 应该返回错误
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_fallback_chain(self):
        """测试降级链路."""
        from data_sources.capital_flow_manager import CapitalFlowManager
        
        mgr = CapitalFlowManager()
        
        # 测试一个可能失败的股票
        result = await mgr.get_capital_flow("002202")
        
        # 无论成功失败，都应该有 source 标注
        assert "source" in result
        assert result["source"] in ["ths", "em", "tencent", "akshare", "unknown"]
        
        await mgr.close()


class TestCapitalFlowManagerMock:
    """资本流管理器 Mock 测试."""
    
    @pytest.mark.asyncio
    async def test_mock_ths_success(self, mocker):
        """Mock 同花顺成功."""
        from data_sources.capital_flow_manager import CapitalFlowManager
        
        # Mock THS
        mock_ths = mocker.patch.object(CapitalFlowManager, '_get_ths')
        mock_ths.return_value.get_capital_flow.return_value = {
            "code": "002202",
            "source": "ths",
            "data_points": 121,
        }
        
        mgr = CapitalFlowManager()
        result = await mgr.get_capital_flow("002202")
        
        assert result["source"] == "ths"
        assert result["data_points"] == 121
        
        await mgr.close()
    
    @pytest.mark.asyncio
    async def test_mock_em_fallback(self, mocker):
        """Mock 东方财富失败降级."""
        from data_sources.capital_flow_manager import CapitalFlowManager
        
        # Mock THS 失败
        mock_ths = mocker.patch.object(CapitalFlowManager, '_get_ths')
        mock_ths.return_value.get_capital_flow.side_effect = Exception("THS 失败")
        
        # Mock EM 成功
        mock_em = mocker.patch.object(CapitalFlowManager, '_get_em')
        mock_em.return_value.get_main_flow.return_value = {
            "main_net_inflow_wan": 10000,
            "signal": "主力流入",
        }
        
        mgr = CapitalFlowManager()
        result = await mgr.get_capital_flow("002202")
        
        # 应该降级到 EM
        assert result["source"] == "em_main"
        
        await mgr.close()
