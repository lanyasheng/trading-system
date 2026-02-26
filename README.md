# Trading Spider 🕷️

> An AI-powered multi-market trading monitor and analysis system built on OpenClaw. Covers A-shares, US stocks, Hong Kong stocks, precious metals, crude oil, and industrial metals.

**English** | [中文](README.zh-CN.md)

## Why Trading Spider?

Most AI trading bots fall into two traps: they either chase momentum (buy high, sell low) or they hallucinate data. Trading Spider tackles both:

- **Anti-momentum scoring**: The system _penalizes_ stocks that are already surging, preventing the classic retail mistake of buying at the top
- **Data-first architecture**: Every number comes from verified API calls — the agent is forbidden from making up prices or indicators
- **Multi-source resilience**: If one data source goes down, automatic fallback chains keep the system running

## Architecture

### Three-Layer Design

```
┌──────────────────────────────────────────────────────────────────┐
│                     Layer 1: Orchestration                       │
│  OpenClaw Gateway (Node.js) → Cron Scheduler → Agent Loop       │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │ Discord Bot  │  │ Cron Engine  │  │ LLM Agent (qwen3.5+) │  │
│  │ (Push/Pull)  │  │ (12 jobs)    │  │ SOUL.md rules         │  │
│  └─────────────┘  └──────────────┘  └───────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│                     Layer 2: Analysis Engine                     │
│  quant.py CLI → 19 atomic tools → Shared infrastructure         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │ Scoring V2   │  │ Technical    │  │ Capital Flow          │  │
│  │ (5-dim+anti) │  │ (MACD/RSI/  │  │ (bid-ask/volume/      │  │
│  │              │  │  KDJ/MA)     │  │  main capital)        │  │
│  └─────────────┘  └──────────────┘  └───────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│                     Layer 3: Data Acquisition                    │
│  8 providers → Fallback chains → Circuit breaker → Cache        │
│  ┌──────┐ ┌──────┐ ┌──────────┐ ┌─────┐ ┌──────────────────┐  │
│  │Tencen│ │ Sina │ │EastMoney │ │ THS │ │ yfinance (US fb) │  │
│  └──┬───┘ └──┬───┘ └────┬─────┘ └──┬──┘ └────────┬─────────┘  │
│     │        │          │          │              │             │
│  ┌──▼────────▼──────────▼──────────▼──────────────▼──────────┐  │
│  │          Fallback Chain + Circuit Breaker                  │  │
│  │  ┌────────────┐ ┌──────────────┐ ┌──────────────────────┐ │  │
│  │  │Rate Limiter│ │Random Delay  │ │UA Rotation           │ │  │
│  │  │ ≤1 req/s   │ │ 0.5-2s       │ │ Anti-ban             │ │  │
│  │  └────────────┘ └──────────────┘ └──────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    3-Tier Cache                             │  │
│  │  SQLite (90d K-lines) │ JSON (60d logs) │ Memory (60s/10m)│  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Market opens
    │
    ▼
┌─────────────────────┐     ┌──────────────┐     ┌──────────────┐
│  Data Sources (8)   │────▶│ Cache Layer   │────▶│ Analysis     │
│  Tencent/Sina/EM... │     │ SQLite+JSON+  │     │ Engine       │
│                     │     │ Memory        │     │ (scoring.py) │
└─────────────────────┘     └──────────────┘     └──────┬───────┘
                                                        │
              ┌─────────────────────────────────────────┤
              │                                         │
              ▼                                         ▼
    ┌──────────────────┐                    ┌──────────────────┐
    │ Anomaly Detection│                    │ 5-Dim Score      │
    │ - Limit up/down  │                    │ - Technical 25%  │
    │ - Volume spikes  │                    │ - Capital  30%   │
    │ - Capital flow   │                    │ - Fund.    10%   │
    │ - Sector rotation│                    │ - Sentiment 20%  │
    └────────┬─────────┘                    │ - Market   15%   │
             │                              └────────┬─────────┘
             │                                       │
             └───────────────┬───────────────────────┘
                             │
                             ▼
                   ┌──────────────────┐
                   │ Anti-Momentum    │
                   │ Filter           │
                   │ - Limit-up -12pt │
                   │ - RSI>80 cap     │
                   │ - KDJ blunting   │
                   │ - Trend penalty  │
                   └────────┬─────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │ Signal Output    │
                   │ STRONG_BUY/BUY/  │
                   │ WATCH/SELL/...   │
                   └────────┬─────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │ Discord Report   │
                   │ (auto-segmented) │
                   └──────────────────┘
```

## Multi-Level Fallback System

The system is designed to never go silent. If a data source fails, it gracefully degrades:

### Source Fallback Chains

| Market | Primary | Secondary | Tertiary | If All Fail |
|--------|---------|-----------|----------|-------------|
| A-shares | Tencent | Sina | EastMoney | Report "data unavailable" |
| US stocks | Tencent US | yfinance | — | Use last cached data |
| HK stocks | Tencent HK | — | — | Report "data unavailable" |
| Commodities | Sina Commodity | — | — | Report "data unavailable" |
| Northbound | EastMoney | — | — | Use daily cache log |
| Limit pool | THS | — | — | Skip anomaly section |
| News | EastMoney | Cailian | Jin10 + Sina + WSJ | Partial report |

### Circuit Breaker Pattern

Each data source has an independent circuit breaker:

```
Normal ──[5 consecutive failures]──▶ Open (60s pause)
                                          │
                                     [60s elapsed]
                                          │
                                          ▼
                                    Half-Open (probe)
                                     │           │
                                  [success]    [fail]
                                     │           │
                                     ▼           ▼
                                  Normal      Open (reset timer)
```

- **Threshold**: 5 consecutive failures trigger circuit open
- **Recovery**: 60-second pause, then probe with a single request
- **Anti-ban**: Random delay (0.5-2s) + User-Agent rotation + ≤1 req/s rate limit

### 3-Tier Cache Strategy

| Tier | Storage | TTL | What it Caches | Why |
|------|---------|-----|----------------|-----|
| **L1: Memory** | In-process dict | 60s / 10min | Market sentiment, HS300 consecutive | Avoid hammering APIs for hot data |
| **L2: JSON file** | `cache/daily_market_log.json` | 60 days | Daily HS300 %, northbound flow | Historical trend calculation |
| **L3: SQLite** | `stock_data/cache.db` | Daily refresh | 90-day K-lines for all watchlist | Technical indicator input |

Cache warm-up runs daily at 08:50 CST before market open.

## Scoring Engine V2

### 5-Dimension Model

| Dimension | Weight | Indicators | Edge Cases |
|-----------|--------|------------|------------|
| **Technical** | 25% | MACD cross, RSI(14+6), KDJ, MA(5/20/60/120), MA alignment | KDJ golden cross at K>80 → penalty instead of bonus |
| **Capital** | 30% | Volume ratio, turnover rate, bid-ask spread, volume-direction | High volume + price drop = escape signal (-5pts) |
| **Fundamental** | 10% | PE by industry (15 sectors), PB | Bank PE<8 normal, Tech PE 20-40 normal |
| **Sentiment** | 20% | 5-source news sentiment, market sentiment index | Negative news -3pts, positive +2pts (asymmetric) |
| **Market** | 15% | HS300/CSI500/SSE50/ChiNext real-time, consecutive trend | 3-day rally -5pts, 5-day rally -10pts |

### Anti-Momentum Mechanism (Why We're Different)

Most scoring systems reward momentum — if a stock is going up, they score it higher, leading to buy-high-sell-low behavior. Trading Spider does the opposite:

| Condition | Penalty | Rationale |
|-----------|---------|-----------|
| Limit-up (涨停) | -12 pts | Can't buy next day (T+1), high chase risk |
| Big rise (≥5%) | -6 pts | Short-term overbought |
| RSI > 80 | Signal capped at WATCH | Overbought, no buy signal allowed |
| KDJ K>80 golden cross | -1 instead of +4 | High-level blunting |
| High volume + surge | -3 pts | Chasing risk signal |
| High volume + plunge | -5 pts | Capital escape signal |
| 3-day consecutive rise | -5 pts | Mean reversion pressure |
| 5-day consecutive rise | -10 pts | Strong mean reversion |
| Northbound 3-day outflow | -4 pts | Foreign capital leaving |
| Northbound 5-day outflow | -8 pts | Sustained foreign selling |
| Limit-down (跌停) | +8 pts | Oversold bounce potential |
| Big drop (≥5%) | +4 pts | Contrarian opportunity |

### Industry-Specific PE Thresholds

The system doesn't apply a universal PE threshold. Instead, it uses industry-specific scoring:

| Industry | Low PE (Cheap) | Fair PE | High PE (Expensive) |
|----------|---------------|---------|---------------------|
| Banking | < 5 | 5-8 | > 10 |
| Real Estate | < 8 | 8-15 | > 20 |
| Technology | < 20 | 20-40 | > 60 |
| Consumer | < 15 | 15-30 | > 45 |
| Healthcare | < 20 | 20-35 | > 50 |
| Utilities | < 10 | 10-20 | > 30 |
| ... | (15 industries total) | | |

### Signal Levels

| Signal | Score | Action |
|--------|-------|--------|
| 🔥 STRONG_BUY | ≥78 | Multi-dimension resonance, strong buy |
| BUY | ≥63 | Conditions met, suggest buy |
| WATCH | 40-63 | Monitor, no action |
| SELL | ≤22 | Deteriorating, consider sell |
| ⚠️ STRONG_SELL | <18 | Multi-dimension decline, strong sell |
| HOLD | Other | Maintain position |

## 19 Analysis Tools

| # | Tool | Description | Sources | Avg Latency |
|---|------|-------------|---------|-------------|
| 1 | `stock_analysis` | 5-dimension stock scoring | Tencent → Sina → EM | ~3s |
| 2 | `weekly_review` | Weekly portfolio review | K-line cache + News | ~3s |
| 3 | `us_stock` | US stock quotes (17 symbols) | Tencent US → yfinance | ~0.5s |
| 4 | `hk_stock` | HK stock quotes | Tencent HK | ~0.2s |
| 5 | `commodity` | 19 commodities (metals/oil/agri) | Sina Commodity | ~0.5s |
| 6 | `global_overview` | One-shot global market view | Multi-source | ~1s |
| 7 | `market_anomaly` | Limit-up/down pool + real industry tags | THS + EastMoney | ~0.4s |
| 8 | `market_scan` | Full A-share gainers/losers/volume | Sina | ~1s |
| 9 | `top_amount` | Top N by trading volume | Sina | ~0.3s |
| 10 | `capital_flow` | Per-stock capital flow (minute-level) | THS | ~0.7s |
| 11 | `northbound_flow` | Northbound capital real-time | EastMoney | ~0.2s |
| 12 | `news_sentiment` | 5-source news + sentiment scoring | EM/Cailian/Jin10/Sina/WSJ | ~1s |
| 13 | `gold_analysis` | Gold/Silver deep (support/resistance/ETF) | Sina + EastMoney | ~1s |
| 14 | `margin_data` | Margin trading balance | EastMoney | ~0.5s |
| 15 | `lhb` | Dragon-tiger list (institutional activity) | EastMoney | ~0.5s |
| 16 | `main_flow` | Main capital net inflow | EastMoney | ~0.5s |
| 17 | `save_daily` | Daily market snapshot caching | EastMoney | ~0.5s |
| 18 | `system_health` | Data source health check | Internal | instant |
| 19 | `warm_klines` | K-line cache warm-up | Tencent → SQLite | ~30s |

## Cron Schedule

### Trading Day (Mon-Fri, CST)

```
08:50  ┌── K-line warm-up ──────────────────────────────────┐
       │   Fetch 90d K-lines for all watchlist stocks        │
09:24  ├── Opening auction monitor ─────────────────────────┤
       │   Detect pre-market capital positioning              │
09:30  ├── Intraday loop (every 10min) ─────────────────────┤
       │   watchlist snapshot + anomaly scan + capital flow    │
14:50  ├── Closing auction monitor ─────────────────────────┤
       │   Detect end-of-day capital grabbing                 │
15:05  ├── Daily closing summary (10-step analysis) ────────┤
       │   Full report: scoring + LHB + margin + sentiment    │
       │   + save_daily (cache today's snapshot)              │
       └────────────────────────────────────────────────────┘

21:30  ┌── US market loop (every 30min) ────────────────────┐
       │   US stocks + commodities + gold/silver              │
05:30  ├── US close summary ────────────────────────────────┤
       │   Impact analysis for next A-share session           │
       └────────────────────────────────────────────────────┘

Sat    ┌── Weekly review ───────────────────────────────────┐
10:00  │   17 watchlist stocks + global macro + sector rotation│
       └────────────────────────────────────────────────────┘
```

## Agent Design

Trading Spider uses a "fat toolbox + thin skill" architecture, where:

- **1 Skill** (`trading-quant`) serves as the unified entry point
- **19 atomic tools** share the same data infrastructure
- **SOUL.md** defines identity, rules, anti-hallucination constraints, and tool routing
- **AGENTS.md** defines session startup, memory, and output formatting rules

This is intentionally different from multi-skill architectures (where each function is a separate skill), because:

1. **Context preservation**: All analysis happens in one conversation turn
2. **Code reuse**: All tools share fallback chains, circuit breakers, and caches
3. **Single maintenance point**: Scoring changes only need one edit

Inspired by [TradingAgents](https://github.com/TauricResearch/TradingAgents)'s multi-perspective debate pattern, the system recommends bull/bear dual-view analysis for major decisions.

## Project Structure

```
workspace-trading/
├── README.md                        # English docs
├── README.zh-CN.md                  # Chinese docs
├── SOUL.md                          # Agent identity, rules, tool routing
├── AGENTS.md                        # Multi-agent collaboration rules
├── MEMORY.md                        # Cross-session lessons learned
├── HEARTBEAT.md                     # Cron heartbeat status
├── mcp-server/                      # Quant Core (Python)
│   ├── data_sources/                # 8 data source adapters
│   │   ├── tencent.py               # A-share primary
│   │   ├── tencent_us.py            # US stock primary
│   │   ├── tencent_hk.py            # HK stock primary
│   │   ├── sina.py                  # A-share secondary
│   │   ├── sina_commodity.py        # Commodities primary
│   │   ├── sina_market.py           # Market scan
│   │   ├── eastmoney.py             # A-share tertiary
│   │   ├── eastmoney_market.py      # LHB, margin, main capital
│   │   ├── eastmoney_news.py        # News source
│   │   ├── eastmoney_northbound.py  # Northbound flow
│   │   ├── ths.py / ths_market.py   # Tonghuashun (limit pool)
│   │   ├── multi_news.py            # 5-source news aggregator
│   │   ├── manager.py               # Source manager + K-line cache
│   │   └── base.py                  # Base (fallback/circuit breaker)
│   ├── analysis/
│   │   ├── scoring.py               # Scoring V2 (5-dim + anti-momentum)
│   │   ├── technical.py             # Technical indicators
│   │   └── capital_flow.py          # Capital flow analysis
│   ├── utils/cache.py               # Cache (KV + daily log + K-line calc)
│   ├── config/settings.yaml         # Weights, thresholds, watchlist
│   └── server.py                    # MCP Server (standby)
├── skills/trading-quant/
│   ├── SKILL.md                     # Tool catalog & usage
│   └── scripts/quant.py             # CLI wrapper (19 tool entry points)
├── stock_data/
│   ├── cache.db                     # SQLite K-line cache (50K+ rows)
│   └── manager.py                   # StockDataManager
└── knowledge/
    ├── watchlist.json               # Watchlist (authoritative source)
    ├── decisions/                   # Trading decision records
    └── macro.md                     # Macro data notes
```

## Getting Started

### Prerequisites

- Python 3.12+ on macOS (tested on M1 Max)
- [OpenClaw CLI](https://github.com/openclaw) installed and configured
- A Discord bot token (for automated reports)
- API access to Chinese market data (free tiers of Tencent/Sina/EastMoney)

### Installation

```bash
# 1. Clone
git clone https://github.com/lanyasheng/trading-system.git
cd trading-system

# 2. Python deps
cd mcp-server
python3 -m venv .venv && source .venv/bin/activate
pip install httpx pyyaml pandas-ta

# 3. Configure OpenClaw
openclaw init
# Add model API keys and Discord token to ~/.openclaw/openclaw.json

# 4. Start
openclaw gateway install

# 5. Verify
./skills/trading-quant/scripts/quant.py system_health
./skills/trading-quant/scripts/quant.py stock_analysis
```

### Configuration

Edit `mcp-server/config/settings.yaml`:

```yaml
watchlist:
  - {code: "002202", name: "金风科技", market: "A"}
  - {code: "600519", name: "贵州茅台", market: "A"}

scoring:
  weights:
    technical: 0.25
    capital: 0.30
    fundamental: 0.10
    sentiment: 0.20
    market: 0.15
  thresholds:
    strong_buy: 78
    buy: 63
    sell: 22
    strong_sell: 18
```

## Roadmap

- [ ] **Backtesting**: Record predictions → compare T+1/3/5 results → accuracy stats → auto-tune weights
- [ ] **Portfolio tracking**: Virtual portfolio → returns vs HS300 benchmark → max drawdown / Sharpe ratio
- [ ] **Report archiving**: Store daily/weekly reports by date for trend analysis
- [ ] **Code convergence**: Unify quant.py and server.py into single entry point
- [ ] **X/Twitter monitoring**: Track key figures (policy makers, industry leaders)
- [ ] **Data quality SLI/SLO**: Source availability P95, latency monitoring, alert on degradation
- [ ] **Multi-model A/B testing**: Compare scoring accuracy across different LLMs
- [ ] **Bull/Bear debate mode**: Multi-agent perspective analysis for major decisions

## Disclaimer

This system is for **research and educational purposes only**. It does not constitute financial advice. Trading involves substantial risk of loss. Past performance does not guarantee future results. Always do your own research before making investment decisions.

## License

MIT
