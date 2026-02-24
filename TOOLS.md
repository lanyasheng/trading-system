# TOOLS.md - Local Notes

## 搜索工具
- **open-websearch**: 免费多引擎搜索（Bing/DuckDuckGo/Exa），通过 mcporter 调用
  - 调用方式: `mcporter call open-websearch.search --args '{"query": "关键词", "limit": 5, "engines": ["bing", "duckduckgo"]}'`
  - 代理已配置: http://127.0.0.1:1087

## 数据源
- a-stock-analysis: A股实时行情（东方财富+新浪，无需key）
- stock-watcher: 自选股监控
- news-aggregator-skill: 财经新闻聚合
- stock-evaluator: 个股评估和买卖推荐
- sector-analyst: 板块轮动分析
- trading-coach: 交易复盘

## 新增工具 (2026-02-24)

### financial-news（多源金融新闻，AKShare）
基于 AKShare 的多源金融新闻聚合，覆盖东方财富、新闻联播、宏观数据、市场情绪。

```bash
# 全部新闻
~/.local/bin/uv run skills/financial-news/scripts/fetch_financial_news.py

# 东方财富快讯
~/.local/bin/uv run skills/financial-news/scripts/fetch_financial_news.py --source eastmoney

# 新闻联播要点（政策信号）
~/.local/bin/uv run skills/financial-news/scripts/fetch_financial_news.py --source cctv

# 宏观数据（CPI/PMI等）
~/.local/bin/uv run skills/financial-news/scripts/fetch_financial_news.py --source macro

# 市场情绪（北向资金/融资余额）
~/.local/bin/uv run skills/financial-news/scripts/fetch_financial_news.py --source sentiment

# 个股新闻
~/.local/bin/uv run skills/financial-news/scripts/fetch_financial_news.py --stock 600519

# 关键词筛选
~/.local/bin/uv run skills/financial-news/scripts/fetch_financial_news.py --keyword "降息,央行"
```

### technical-analysis（技术分析，pandas-ta）
基于 pandas-ta 的 A股技术分析，计算 EMA/RSI/MACD/布林带/KDJ，生成买卖信号。

```bash
# 单只分析
~/.local/bin/uv run skills/technical-analysis/scripts/tech_analyze.py 600519

# 多只分析
~/.local/bin/uv run skills/technical-analysis/scripts/tech_analyze.py 600519 000858 002594

# 周线分析
~/.local/bin/uv run skills/technical-analysis/scripts/tech_analyze.py 600519 --period weekly

# 仅看信号
~/.local/bin/uv run skills/technical-analysis/scripts/tech_analyze.py 600519 --signals
```

**信号说明:**
- 🟢🟢 STRONG_BUY: 多个指标同时给出买入信号（评分>=5）
- 🟢 BUY: 买入信号（评分>=3）
- 🔴🔴 STRONG_SELL: 强烈卖出信号
- 🔴 SELL: 卖出信号
- 🟡 HOLD: 观望

### rss-financial（财经 RSS 聚合，35 源）
基于你提供的高质量 RSS 源，覆盖：
- **flash**: 财联社电报、金十数据、格隆汇快讯（实时性最强）
- **cn_deep**: 财联社/雪球/格隆汇/有知有行（国内深度分析）
- **research**: 东方财富策略/宏观/晨报/行业研报、格隆汇研报
- **hk**: 财联社港股、格隆汇股票
- **intl**: Bloomberg/WSJ/CNBC/MarketWatch/Seeking Alpha/华尔街见闻
- **macro**: 金十数据闪讯、财联社金融/期货

```bash
python3 skills/financial-news/scripts/rss_financial.py                          # 全部
python3 skills/financial-news/scripts/rss_financial.py --category flash         # 快讯
python3 skills/financial-news/scripts/rss_financial.py --category cn_deep       # 国内深度
python3 skills/financial-news/scripts/rss_financial.py --category research      # 研报
python3 skills/financial-news/scripts/rss_financial.py --category intl          # 国际
python3 skills/financial-news/scripts/rss_financial.py --category macro         # 宏观
python3 skills/financial-news/scripts/rss_financial.py --keyword "贵金属,黄金,原油"  # 关键词
```

## AKShare 国际市场支持说明
AKShare 主要支持 A 股数据，但也支持部分国际市场：
- 国际贵金属/原油: 通过 `ak.futures_foreign_commodity_realtime()` 获取
- 国际指数: 通过 `ak.index_investing_global()` 获取
- 汇率: 通过 `ak.currency_boc_safe()` 获取
- 但覆盖度不如专业的国际数据源

对于国际贵金属/原油/地缘政治等信息，**优先使用 rss-financial 的 intl 分类**（Bloomberg/WSJ/CNBC），这些源的覆盖最全面。
