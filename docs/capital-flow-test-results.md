# 资金流数据源测试结果 (2026-02-27)

## 测试结论

### ✅ 稳定可用

| 数据源 | 接口 | 数据类型 | 延迟 | 推荐场景 |
|--------|------|---------|------|---------|
| **同花顺** | `d.10jqka.com.cn/v4/time/hs_{code}/capital.js` | 分钟级资金流 (121 点) | 实时 | 🔥 盘中实时监控 |
| **腾讯财经** | `qt.gtimg.cn/q={code}` | 内外盘差 | 实时 | 🔥 盘中主力替代信号 |
| **AKShare** | `ak.stock_individual_fund_flow()` | 主力/超大单/大单/中单/小单 | T+1 日 | 🟡 盘后复盘分析 |

### ❌ 不稳定/不可用

| 数据源 | 接口 | 问题 | 备注 |
|--------|------|------|------|
| **东方财富主力** | `push2.eastmoney.com/api/qt/stock/fflow/kline/get` | Server disconnected | 偶尔可用，不稳定 |
| **东方财富实时** | `82.push2.eastmoney.com` | ProxyError/Max retries | 网络问题 |
| **AKShare (实时)** | `ak.stock_zh_a_spot_em()` | ProxyError | 底层调用东财接口 |

---

## 推荐的降级链路

### 主力资金净流入 (实时)

```
1️⃣ 同花顺分钟级资金流 (主数据源)
   - 优点：稳定，121 个数据点/天
   - 缺点：无主力/超大单/大单分类，只有成交额

2️⃣ 腾讯内外盘差 (主力替代信号)
   - 外盘 - 内盘 = 主力买卖压力
   - 外盘 > 内盘 → 主力买入信号
   - 外盘 < 内盘 → 主力卖出信号

3️⃣ AKShare 历史资金流 (参考)
   - 用于分析历史主力行为模式
   - 不用于实时交易决策
```

### 北向资金 (实时)

```
1️⃣ 东方财富 (主数据源)
   - 接口已修复，但非交易时段返回 0

2️⃣ AKShare 沪深港通
   - 备用数据源
```

---

## 当前资金评分逻辑

**资金面评分** (`mcp-server/analysis/capital_flow.py`):
```python
# 基础资金流 (腾讯/同花顺)
- 量比 (volume_ratio): +2~+8 分
- 换手率 (turnover_rate): +1~+3 分
- 成交额对比 (amount_ratio): +2~+5 分
- 买卖价差 (spread_pct): +2 分

# 主力资金 (东方财富/AKShare)
- 主力净流入 >5000 万：+10 分
- 主力净流入 >1000 万：+5 分
- 主力净流出 <-5000 万：-10 分
- 主力净流出 <-1000 万：-5 分
- 超大单净流入 >3000 万：+3 分
- 超大单净流出 <-3000 万：-3 分
```

**当前问题**：东方财富主力接口不稳定，导致主力资金评分经常缺失。

---

## 解决方案

### 短期 (已实现)

1. ✅ **同花顺为主数据源** - 分钟级资金流稳定
2. ✅ **腾讯内外盘差作为主力替代** - 当主力数据缺失时使用
3. ✅ **标注数据来源** - 让用户知道何时是完整数据，何时是降级数据

### 中期 (待实现)

1. ⏳ **增加重试机制** - 东方财富接口失败自动重试 2 次
2. ⏳ **实现腾讯内外盘差评分** - 将内外盘差映射为主力资金评分
3. ⏳ **AKShare 历史数据参考** - 用于分析主力行为模式

### 长期

1. ⏳ **自建数据源** - 爬取 + 缓存，减少对外部 API 依赖
2. ⏳ **Moltbook MCP 服务器** - 搜索或自建资金流 MCP 服务

---

## 腾讯内外盘差映射规则 (待实现)

```python
# 腾讯内外盘差 → 主力资金评分映射
outer_inner_diff = outer_volume - inner_volume  # 手

if outer_inner_diff > 100000:  # >10 万手
    score += 10
    signal = "主力大幅流入"
elif outer_inner_diff > 50000:  # >5 万手
    score += 5
    signal = "主力流入"
elif outer_inner_diff < -100000:
    score -= 10
    signal = "主力大幅流出"
elif outer_inner_diff < -50000:
    score -= 5
    signal = "主力流出"
else:
    signal = "主力中性"
```

---

## 测试命令

```bash
# 测试同花顺资金流
./mcp-server/.venv/bin/python3 ./skills/trading-quant/scripts/quant.py capital_flow 002202

# 测试北向资金
./mcp-server/.venv/bin/python3 ./skills/trading-quant/scripts/quant.py northbound_flow

# 测试个股评分 (含资金面)
./mcp-server/.venv/bin/python3 ./skills/trading-quant/scripts/quant.py stock_analysis 002202
```

---

*最后更新：2026-02-27 | 交易蜘蛛数据源测试报告*
