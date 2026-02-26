---
name: trading-quant
description: 量化交易数据分析工具。A股/美股/港股/贵金属实时行情，多维度评分(技术面+资金面+基本面)，涨跌停池，北向资金，分钟级资金流。Use when: (1) 查询任何股票实时行情和评分, (2) 分析A股涨停跌停异动, (3) 查看北向资金流向, (4) 美股港股贵金属行情, (5) 全球市场概览, (6) 个股资金流分析。
---

# 量化交易数据分析

通过腾讯/新浪/东财/同花顺多数据源获取实时行情，提供5维评分体系(技术25%+资金30%+基本面10%+消息20%+情绪15%)。

## 工具列表

### A股分析（含多维评分）
```bash
# 分析自选股（默认priority列表前10只）
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py stock_analysis

# 指定股票代码（逗号分隔）
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py stock_analysis 600519,000858,002202
```

### 周度复盘数据（含周涨跌幅）
```bash
# 获取自选股周度数据（含 week_change_pct 字段）
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py weekly_review
```

### 美股行情
```bash
# 默认美股自选
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py us_stock

# 指定股票
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py us_stock AAPL,NVDA,TSLA
```

### 港股行情
```bash
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py hk_stock 00700,09988,03690
```

### 贵金属/原油
```bash
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py commodity XAU,XAG,WTI,BRENT
```

### 全球市场概览（一键获取所有市场）
```bash
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py global_overview
```

### A股涨停/跌停异动
```bash
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py market_anomaly
```

### A股个股资金流（分钟级）
```bash
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py capital_flow 600519,000858
```

### 北向资金（沪深港通）
```bash
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py northbound_flow
```

### 系统健康检查
```bash
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py system_health
```

### 全A异动扫描（大资金+急拉急跌）
```bash
# 全市场异动一键扫描（涨>5% + 跌>5% + 成交额>5亿）
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py market_scan

# 成交额排行（默认前20）
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py top_amount 20
```

### K线预热（盘前执行）
```bash
{baseDir}/../../../mcp-server/.venv/bin/python3 {baseDir}/scripts/quant.py warm_klines
```

## 评分体系说明

| 维度 | 权重 | 数据源 | 指标 |
|------|------|--------|------|
| 技术面 | 25% | K线 | MACD/RSI/KDJ/均线/布林 |
| 资金面 | 30% | 实时 | 量比/换手率/量价背离 |
| 基本面 | 10% | 实时 | PE/PB/市值 |
| 消息面 | 20% | 待扩展 | 中性默认 |
| 情绪面 | 15% | 待扩展 | 中性默认 |

### 信号等级
- STRONG_BUY (>=80): 强烈买入
- BUY (>=65): 买入
- WATCH (>=50): 观望
- HOLD (>=35): 持有
- SELL (>=20): 卖出
- STRONG_SELL (<20): 强烈卖出

## 数据源优先级

| 市场 | 主源 | 降级1 | 降级2 | 降级3 |
|------|------|-------|-------|-------|
| A股 | 腾讯 | 新浪 | 东财 | 同花顺 |
| 美股 | 腾讯 | yfinance | - | - |
| 港股 | 腾讯 | - | - | - |
| 商品 | 新浪期货 | - | - | - |

## 输出格式

所有工具输出 JSON，包含结构化数据。agent 应基于数据给出建议，禁止编造数据。

## 重要规则

1. **必须使用工具获取数据，禁止凭记忆回答行情问题**
2. **PE>100 或 PB<0.8 时必须在风险提示中说明**
3. **涨停股数>30只时提示市场情绪亢奋**
4. **北向资金净流出>50亿时提示外资撤离风险**
