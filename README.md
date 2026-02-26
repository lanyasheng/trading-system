# Trading Spider — AI 交易盯盘系统

> 基于 OpenClaw + LLM 的全市场智能盯盘系统。覆盖 A 股、美股、港股、贵金属/原油/工业金属。

## 系统架构

```
                    ┌─────────────────────┐
                    │   Discord Client    │ ← 用户交互/报告推送
                    └────────┬────────────┘
                             │
                    ┌────────▼────────────┐
                    │   OpenClaw Gateway  │ ← Cron 调度 + Agent Loop
                    │   (Node.js)         │
                    └────────┬────────────┘
                             │ exec tool
                    ┌────────▼────────────┐
                    │   quant.py (CLI)    │ ← 19 个工具入口
                    └────────┬────────────┘
                             │ import
            ┌────────────────┼────────────────┐
            │                │                │
    ┌───────▼───────┐ ┌─────▼─────┐ ┌────────▼────────┐
    │ data_sources/ │ │ analysis/ │ │ utils/cache.py  │
    │ 8 个数据源    │ │ 评分引擎  │ │ 缓存系统        │
    └───────┬───────┘ └─────┬─────┘ └────────┬────────┘
            │               │                │
    ┌───────▼───────────────▼────────────────▼───────┐
    │           外部 API / SQLite / JSON 文件         │
    │  腾讯 | 新浪 | 东财 | 同花顺 | cache.db        │
    └────────────────────────────────────────────────┘
```

## 工具总览 (19 个)

| 工具 | 功能 | 数据源 |
|------|------|--------|
| `stock_analysis` | 自选股综合评分 (5 维度) | 腾讯→新浪→东财 |
| `weekly_review` | 周度复盘 | K 线缓存 + 新闻 |
| `us_stock` | 美股实时行情 | 腾讯→yfinance |
| `hk_stock` | 港股实时行情 | 腾讯港股 |
| `commodity` | 商品(贵金属/原油/工业金属/黑色系/农产品) | 新浪商品 |
| `market_anomaly` | A 股涨跌停池 + 真实行业分类 | 同花顺 + 东财 |
| `market_scan` | 全 A 涨幅/跌幅/量比排行 | 新浪全 A |
| `top_amount` | 成交额 TOP N | 新浪 |
| `capital_flow` | 个股资金流向 | 同花顺 |
| `northbound_flow` | 北向资金实时净流入 | 东财 |
| `global_overview` | 全球市场概览 | 多源聚合 |
| `system_health` | 数据源健康检查 | 内部 |
| `warm_klines` | K 线缓存预热 | 腾讯 → SQLite |
| `news_sentiment` | 5 源新闻聚合 + 情绪评分 | 东财/财联社/金十/新浪/华尔街见闻 |
| `gold_analysis` | 黄金白银深度分析 (支撑压力/ETF 流) | 新浪 + 东财 |
| `margin_data` | 融资融券余额 | 东财 |
| `lhb` | 龙虎榜 (游资/机构动向) | 东财 |
| `main_flow` | 个股主力资金净流入 | 东财 |
| `save_daily` | 每日市场快照缓存 | 东财 |

## 评分系统 (Scoring V2)

### 五维度权重

| 维度 | 权重 | 核心指标 |
|------|------|----------|
| 技术面 | 25% | MACD, RSI(14+6), KDJ, MA(5/20/60/120), 均线排列 |
| 资金面 | 30% | 量比, 换手率, 买卖价差, 放量方向 |
| 基本面 | 10% | PE 行业分档 (15 个行业), PB |
| 情绪面 | 20% | 5 源新闻情绪, 市场情绪指数 |
| 市场面 | 15% | 沪深300/中证500/上证50/创业板指 |

### 防追涨杀跌机制

- **动量惩罚**: 涨停 -12, 大涨 -6; 跌停 +8, 大跌 +4
- **RSI 限制**: RSI>80 → 信号上限 WATCH; RSI<20 → 保底 WATCH
- **KDJ 高位钝化**: K>80 金叉不加分反 -1
- **量比+方向**: 放量大涨 -3(追高), 放量大跌 -5(出逃)
- **大盘连涨惩罚**: 3 天 -5, 5 天 -10
- **北向连续流出**: 3 天 -4, 5 天 -8
- **评分硬限**: 10-90 分

### 信号体系

| 信号 | 评分范围 | 含义 |
|------|----------|------|
| STRONG_BUY | ≥78 | 多维共振, 强烈买入 |
| BUY | ≥63 | 条件满足, 建议买入 |
| WATCH | 40-63 | 关注但不操作 |
| SELL | ≤22 | 条件恶化, 考虑卖出 |
| STRONG_SELL | <18 | 多维恶化, 强烈卖出 |
| HOLD | 其他 | 维持现状 |

## 数据源架构

### 降级链 (Fallback Chain)

```
A 股行情:  腾讯 → 新浪 → 东财
美股行情:  腾讯美股 → yfinance
港股行情:  腾讯港股
商品期货:  新浪商品
北向资金:  东财
涨跌停池:  同花顺
新闻:     东财 + 财联社 + 金十 + 新浪7x24 + 华尔街见闻
龙虎榜:   东财 (BILLBOARD API)
融资融券:  东财
主力资金:  东财
```

### 防封策略

- 随机延迟 (0.5-2s) + User-Agent 轮换
- 熔断器: 连续 5 次失败 → 暂停 60s → 自动恢复
- 请求频率: 单源 ≤ 1 req/s

## 缓存系统

| 层 | 存储 | TTL | 用途 |
|----|------|-----|------|
| SQLite | `stock_data/cache.db` | 每日盘前刷新 | 个股 90 天 K 线 |
| JSON 文件 | `cache/daily_market_log.json` | 60 天 | 每日沪深300涨跌 + 北向净流入 |
| 内存 | 进程内 dict | 60s | 市场情绪快照 |
| 内存 | 进程内 dict | 10min | K 线连涨/连跌计算 |

## Cron 任务调度

### 交易日时间表 (Asia/Shanghai)

| 时间 | 任务 | 超时 |
|------|------|------|
| 08:50 | K 线缓存预热 | 180s |
| 09:24-09:25 | 集合竞价监控 | 180s |
| 09:30-14:30 (*/10min) | 自选股监控 + 异动检测 | 180s |
| 14:50, 14:55 | 尾盘抢筹/出逃监控 | 180s |
| 15:05 | **收盘总结** (10 步分析) | 360s |
| 21:30-05:00 (*/30min) | 美股快照 | 180s |
| 05:30 | 美股收盘总结 | 360s |
| 每周六 10:00 | 周度复盘 | 360s |
| 每 5 分钟 | 健康监控 | 240s |

### 收盘总结 10 步流程

1. `stock_analysis` — 全部自选股评分
2. `market_anomaly` — 涨跌停池 + 行业分布
3. `northbound_flow` — 北向资金
4. `news_sentiment` — 5 源新闻情绪
5. `commodity` — 商品行情
6. `gold_analysis` — 黄金白银深度
7. `capital_flow` — 异动标的资金流
8. `margin_data` — 融资融券余额
9. `lhb` — 龙虎榜 (游资/机构)
10. `save_daily` — 缓存今日快照

## 目录结构

```
workspace-trading/
├── SOUL.md                          # Agent 身份 + 行为规则
├── AGENTS.md                        # 多 Agent 协作规则
├── HEARTBEAT.md                     # 心跳配置
├── mcp-server/                      # Quant Core (Python 量化分析库)
│   ├── data_sources/                # 8 个数据源适配器
│   │   ├── tencent.py              # 腾讯行情 (A 股主力)
│   │   ├── tencent_us.py           # 腾讯美股
│   │   ├── tencent_hk.py           # 腾讯港股
│   │   ├── sina.py                 # 新浪 (A 股降级)
│   │   ├── sina_commodity.py       # 新浪商品期货
│   │   ├── sina_market.py          # 新浪全 A 排行
│   │   ├── eastmoney.py            # 东财 (A 股降级)
│   │   ├── eastmoney_market.py     # 东财市场 (融资融券/龙虎榜/主力)
│   │   ├── eastmoney_news.py       # 东财新闻
│   │   ├── eastmoney_northbound.py # 东财北向资金
│   │   ├── ths.py                  # 同花顺 (涨跌停池)
│   │   ├── ths_market.py           # 同花顺市场扫描
│   │   ├── multi_news.py           # 5 源新闻聚合
│   │   ├── manager.py             # 数据源管理器 + K 线缓存
│   │   └── base.py                # 基础类 (降级/熔断/限流)
│   ├── analysis/                   # 分析引擎
│   │   ├── scoring.py             # 评分 V2 (5 维度 + 防追涨杀跌)
│   │   ├── technical.py           # 技术指标计算
│   │   └── capital_flow.py        # 资金流分析
│   ├── utils/
│   │   └── cache.py               # 缓存系统 (KV + 日志 + K 线)
│   ├── config/
│   │   └── settings.yaml          # 评分权重/阈值/自选股配置
│   └── server.py                   # MCP Server (备用, 当前未激活)
├── skills/trading-quant/
│   ├── SKILL.md                    # 工具清单 + 用法说明
│   └── scripts/quant.py           # CLI Wrapper (exec 入口)
├── stock_data/
│   ├── cache.db                   # SQLite K 线缓存
│   └── manager.py                 # StockDataManager
├── cache/
│   └── daily_market_log.json      # 每日市场快照日志
└── scripts/                        # 辅助脚本
    ├── monitor_v2.py              # 增强监控
    └── commodities_monitor.py     # 商品监控
```

## 后续路线图

### Phase 5: 回测系统 (计划中)

- **预测记录**: 每次发出信号时记录 {stock, signal, score, price, time}
- **结果比对**: T+1/T+3/T+5 实际涨跌与预测方向比对
- **准确率统计**: 按信号类型/板块/时间段统计准确率
- **权重自适应**: 根据准确率自动调整五维度权重

### Phase 6: 回报追踪

- 模拟仓位管理 (虚拟盘)
- 收益率计算 (vs 沪深300 基准)
- 最大回撤/夏普比率

### 待优化

- [ ] 日报/周报归档 (按日期存储历史报告)
- [ ] quant.py 与 server.py 双实现收敛 (统一为单一入口)
- [ ] 增加监控标的: 银行 ETF, 科创 100 ETF, 港股互联网
- [ ] X/Twitter 关键人物监控 (川普/马斯克)
- [ ] 数据质量 SLI/SLO 度量 (数据源可用率/延迟 P95)
- [ ] 多模型 A/B 测试 (qwen vs kimi vs glm 评分对比)

## 部署

### 环境要求

- macOS (M1 Max 或更高)
- Python 3.12+
- OpenClaw CLI (已安装并配置)
- Discord Bot Token (已配置)

### 启动

```bash
# 1. 安装 Python 依赖
cd mcp-server && uv sync

# 2. 启动 OpenClaw Gateway
openclaw gateway install

# 3. 验证工具可用
quant.py system_health
quant.py stock_analysis
```

### 手动触发 Cron

```bash
openclaw cron run <job-id> --timeout 360
```
