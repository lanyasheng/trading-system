# 交易蜘蛛 🕷️

> 基于 OpenClaw 构建的 AI 多市场交易监控与分析系统。覆盖 A 股、美股、港股、贵金属、原油及工业金属。

[English](README.md) | **中文**

## 功能特性

- **多市场覆盖**：A 股、美股（NASDAQ/NYSE）、港股、贵金属、原油、工业金属、黑色系、农产品
- **五维评分引擎**：技术面（MACD/RSI/KDJ/均线）、资金面、基本面（分行业 PE/PB）、情绪面（5 源新闻）、大盘面
- **反追涨杀跌机制**：涨停扣分、RSI 超买降级、KDJ 高位钝化、量价方向分析、连涨天数惩罚
- **实时异动检测**：急拉急跌预警、量能异动、资金异动、板块轮动追踪
- **19 个分析工具**：个股评分、市场扫描、北向资金、龙虎榜、融资融券、黄金白银深度分析等
- **多源数据**：腾讯、新浪、东方财富、同花顺，自动回退链
- **智能缓存**：SQLite 缓存 K 线、JSON 缓存日快照、内存缓存实时数据
- **Discord 集成**：通过 Discord 机器人自动推送定时报告

## 系统架构

```
                    ┌─────────────────────┐
                    │   Discord / 对话    │ ← 用户交互与报告推送
                    └────────┬────────────┘
                             │
                    ┌────────▼────────────┐
                    │   OpenClaw Gateway  │ ← 定时任务调度 + Agent 循环
                    │   (Node.js)         │
                    └────────┬────────────┘
                             │ exec 工具调用
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
    │       外部 API / SQLite / JSON 文件            │
    │  腾讯 | 新浪 | 东方财富 | 同花顺 | cache.db    │
    └────────────────────────────────────────────────┘
```

## 工具列表

| 工具 | 功能 | 数据源 |
|------|------|--------|
| `stock_analysis` | 五维度综合评分 | 腾讯 → 新浪 → 东财 |
| `weekly_review` | 周度自选股复盘 | K 线缓存 + 新闻 |
| `us_stock` | 美股实时行情 | 腾讯美股 → yfinance |
| `hk_stock` | 港股实时行情 | 腾讯港股 |
| `commodity` | 大宗商品（金属/油/农产品） | 新浪商品 |
| `market_anomaly` | A 股涨跌停池 + 真实行业标签 | 同花顺 + 东财 |
| `market_scan` | 全 A 涨跌幅/成交量排行 | 新浪 |
| `top_amount` | 成交额 TOP N | 新浪 |
| `capital_flow` | 个股资金流向 | 同花顺 |
| `northbound_flow` | 北向资金实时流入 | 东方财富 |
| `global_overview` | 全球市场概览 | 多数据源 |
| `news_sentiment` | 5 源新闻聚合 + 情绪评分 | 东财/财联社/金十/新浪/华尔街见闻 |
| `gold_analysis` | 黄金白银深度分析（支撑/压力/ETF） | 新浪 + 东财 |
| `margin_data` | 融资融券余额 | 东方财富 |
| `lhb` | 龙虎榜（机构动向） | 东方财富 |
| `main_flow` | 主力资金净流入 | 东方财富 |
| `save_daily` | 每日市场快照缓存 | 东方财富 |
| `system_health` | 数据源健康检查 | 内部 |
| `warm_klines` | K 线缓存预热 | 腾讯 → SQLite |

## 评分系统

### 五维度模型（V2）

| 维度 | 权重 | 关键指标 |
|------|------|----------|
| 技术面 | 25% | MACD、RSI（14+6 日）、KDJ、均线（5/20/60/120）、均线多头排列 |
| 资金面 | 30% | 量比、换手率、委比、量价方向 |
| 基本面 | 10% | 分行业 PE（15 个行业阈值）、PB |
| 情绪面 | 20% | 5 源新闻情绪、大盘情绪指数 |
| 大盘面 | 15% | 沪深 300/中证 500/上证 50/创业板实时表现 |

### 反追涨杀跌机制

防止追高杀跌：

- **动量惩罚**：涨停 -12 分、大涨 -6 分；跌停 +8 分、大跌 +4 分
- **RSI 限制**：RSI>80 时信号上限为 WATCH；RSI<20 时下限为 WATCH
- **KDJ 高位钝化**：K>80 时金叉不加 4 分而是扣 1 分
- **量价方向**：放量急拉 -3 分（追高风险）、放量暴跌 -5 分（出逃信号）
- **连涨惩罚**：连涨 3 天 -5 分、连涨 5 天 -10 分
- **北向流出**：连续 3 日净流出 -4 分、5 日 -8 分

### 信号级别

| 信号 | 分数区间 | 操作建议 |
|------|---------|----------|
| STRONG_BUY | ≥78 | 多维共振，强烈买入 |
| BUY | ≥63 | 条件满足，建议买入 |
| WATCH | 40-63 | 关注观望，暂不操作 |
| SELL | ≤22 | 指标恶化，考虑卖出 |
| STRONG_SELL | <18 | 多维下行，强烈卖出 |
| HOLD | 其他 | 维持持仓 |

## 数据源架构

### 回退链

```
A 股:      腾讯 → 新浪 → 东方财富
美股:      腾讯美股 → yfinance
港股:      腾讯港股
大宗商品:  新浪商品
北向资金:  东方财富
涨跌停池:  同花顺
新闻:      东方财富 + 财联社 + 金十 + 新浪 7x24 + 华尔街见闻
龙虎榜:    东方财富（BILLBOARD API）
融资融券:  东方财富
主力资金:  东方财富
```

### 反封禁策略

- 随机延迟（0.5-2 秒）+ User-Agent 轮换
- 熔断器：连续 5 次失败 → 暂停 60 秒 → 自动恢复
- 频率限制：每源 ≤1 请求/秒

## 缓存架构

| 层级 | 存储 | TTL | 用途 |
|------|------|-----|------|
| SQLite | `stock_data/cache.db` | 每日刷新 | 自选股 90 天 K 线 |
| JSON 文件 | `cache/daily_market_log.json` | 60 天 | 每日沪深 300 涨跌 + 北向资金 |
| 内存 | 进程内字典 | 60 秒 | 大盘情绪快照 |
| 内存 | 进程内字典 | 10 分钟 | 沪深 300 连涨/连跌天数计算 |

## 定时任务（交易日）

| 时间（北京时间） | 任务 | 超时 |
|-----------------|------|------|
| 08:50 | K 线缓存预热 | 180s |
| 09:24-09:25 | 开盘集合竞价监控 | 180s |
| 09:30-14:30（每 10 分钟） | 自选股监控 + 异动检测 | 180s |
| 14:50, 14:55 | 尾盘集合竞价监控 | 180s |
| 15:05 | **收盘总结**（10 步分析） | 360s |
| 21:30-05:00（每 30 分钟） | 美股快照 | 180s |
| 05:30 | 美股收盘总结 | 360s |
| 周六 10:00 | 周度复盘 | 360s |

## 项目结构

```
workspace-trading/
├── README.md                        # 英文文档
├── README.zh-CN.md                  # 中文文档（本文件）
├── SOUL.md                          # Agent 身份与行为规则
├── AGENTS.md                        # 多 Agent 协作规则
├── mcp-server/                      # 量化核心（Python 分析库）
│   ├── data_sources/                # 8 个数据源适配器
│   │   ├── tencent.py / tencent_us.py / tencent_hk.py
│   │   ├── sina.py / sina_commodity.py / sina_market.py
│   │   ├── eastmoney.py / eastmoney_market.py / eastmoney_news.py
│   │   ├── ths.py / ths_market.py
│   │   ├── multi_news.py           # 5 源新闻聚合器
│   │   ├── manager.py              # 数据源管理器 + K 线缓存
│   │   └── base.py                 # 基类（回退链/熔断器）
│   ├── analysis/
│   │   ├── scoring.py              # 评分 V2（五维度 + 反追涨杀跌）
│   │   ├── technical.py            # 技术指标计算
│   │   └── capital_flow.py         # 资金流向分析
│   ├── utils/cache.py              # 缓存系统（KV + 日志 + K 线）
│   ├── config/settings.yaml        # 权重、阈值、自选股配置
│   └── server.py                   # MCP Server（待机状态）
├── skills/trading-quant/
│   ├── SKILL.md                    # 工具清单与用法
│   └── scripts/quant.py            # CLI 入口（exec 调用点）
├── stock_data/
│   ├── cache.db                    # SQLite K 线缓存
│   └── manager.py                  # StockDataManager
└── knowledge/
    ├── watchlist.json              # 自选股列表（权威源）
    ├── decisions/                  # 决策记录
    └── macro.md                    # 宏观数据
```

## 快速开始

### 环境要求

- Python 3.12+
- [OpenClaw CLI](https://github.com/openclaw) 已安装配置
- Discord 机器人 Token（用于自动推送）

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/lanyasheng/trading-system.git
cd trading-system

# 2. 安装 Python 依赖
cd mcp-server
uv sync  # 或: pip install -r requirements.txt

# 3. 配置 OpenClaw
openclaw init
# 编辑 ~/.openclaw/openclaw.json，添加模型 API Key 和 Discord Token

# 4. 启动网关
openclaw gateway install

# 5. 验证工具
./skills/trading-quant/scripts/quant.py system_health
./skills/trading-quant/scripts/quant.py stock_analysis
```

### 配置

编辑 `mcp-server/config/settings.yaml` 自定义：

```yaml
watchlist:
  - {code: "002202", name: "你的股票", market: "A"}

scoring:
  weights:
    technical: 0.25
    capital: 0.30
    fundamental: 0.10
    sentiment: 0.20
    market: 0.15
```

## 路线图

- [ ] **回测系统**：记录预测 → 对比 T+1/3/5 实际结果 → 准确率统计 → 自动调参
- [ ] **组合跟踪**：虚拟持仓 → 对比沪深 300 基准收益 → 最大回撤 / 夏普比率
- [ ] **报告归档**：按日期存储日报和周报
- [ ] **代码收敛**：统一 quant.py 和 server.py 为单一入口
- [ ] **X/推特监控**：追踪关键人物（政策制定者、行业领袖）
- [ ] **数据质量 SLI/SLO**：数据源可用性和延迟 P95 指标
- [ ] **多模型 A/B 测试**：对比不同 LLM 的评分准确度

## 免责声明

本系统**仅供研究和学习使用**，不构成任何投资建议。交易存在重大风险，请在做出投资决策前进行独立研究。

## 许可证

MIT
