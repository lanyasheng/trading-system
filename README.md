# Trading Spider 🕷️

> An AI-powered multi-market trading monitor and analysis system built on OpenClaw. Covers A-shares, US stocks, Hong Kong stocks, precious metals, crude oil, and industrial metals.

## Features

- **Multi-market coverage**: A-shares, US stocks (NASDAQ/NYSE), HK stocks, precious metals, crude oil, industrial metals, black commodities, agricultural products
- **5-dimension scoring engine**: Technical (MACD/RSI/KDJ/MA), Capital flow, Fundamental (PE/PB by industry), Sentiment (5-source news), Market overview
- **Anti-momentum protection**: Limit-up penalty, RSI caps, KDJ high blunting, volume-direction analysis, consecutive trend penalty
- **Real-time anomaly detection**: Price surge/plunge alerts, volume spikes, capital flow abnormalities, sector rotation tracking
- **19 analysis tools**: Stock scoring, market scan, northbound flow, dragon-tiger list, margin data, gold/silver deep analysis, and more
- **Multi-source data**: Tencent, Sina, EastMoney, THS with automatic fallback chains
- **Smart caching**: SQLite for K-lines, JSON for daily snapshots, in-memory for real-time data
- **Discord integration**: Automated reports via Discord bot with scheduled cron jobs

## Architecture

```
                    ┌─────────────────────┐
                    │   Discord / Chat    │ ← User interaction & reports
                    └────────┬────────────┘
                             │
                    ┌────────▼────────────┐
                    │   OpenClaw Gateway  │ ← Cron scheduler + Agent loop
                    │   (Node.js)         │
                    └────────┬────────────┘
                             │ exec tool
                    ┌────────▼────────────┐
                    │   quant.py (CLI)    │ ← 19 tool entry points
                    └────────┬────────────┘
                             │ import
            ┌────────────────┼────────────────┐
            │                │                │
    ┌───────▼───────┐ ┌─────▼─────┐ ┌────────▼────────┐
    │ data_sources/ │ │ analysis/ │ │ utils/cache.py  │
    │ 8 providers   │ │ Scoring   │ │ Cache system    │
    └───────┬───────┘ └─────┬─────┘ └────────┬────────┘
            │               │                │
    ┌───────▼───────────────▼────────────────▼───────┐
    │         External APIs / SQLite / JSON files    │
    │  Tencent | Sina | EastMoney | THS | cache.db   │
    └────────────────────────────────────────────────┘
```

## Tools

| Tool | Description | Data Sources |
|------|-------------|--------------|
| `stock_analysis` | Comprehensive 5-dimension stock scoring | Tencent → Sina → EastMoney |
| `weekly_review` | Weekly portfolio review | K-line cache + News |
| `us_stock` | US stock real-time quotes | Tencent US → yfinance |
| `hk_stock` | HK stock real-time quotes | Tencent HK |
| `commodity` | Commodities (metals/oil/agriculture) | Sina Commodity |
| `market_anomaly` | A-share limit-up/down pool + real industry tags | THS + EastMoney |
| `market_scan` | Full A-share gainers/losers/volume ranking | Sina |
| `top_amount` | Top N by trading volume | Sina |
| `capital_flow` | Individual stock capital flow | THS |
| `northbound_flow` | Northbound capital real-time flow | EastMoney |
| `global_overview` | Global market overview | Multi-source |
| `news_sentiment` | 5-source news aggregation + sentiment scoring | EastMoney/Cailian/Jin10/Sina/WSJ |
| `gold_analysis` | Gold/Silver deep analysis (support/resistance/ETF) | Sina + EastMoney |
| `margin_data` | Margin trading balance | EastMoney |
| `lhb` | Dragon-tiger list (institutional activity) | EastMoney |
| `main_flow` | Main capital net inflow | EastMoney |
| `save_daily` | Daily market snapshot caching | EastMoney |
| `system_health` | Data source health check | Internal |
| `warm_klines` | K-line cache warm-up | Tencent → SQLite |

## Scoring System

### 5-Dimension Model (V2)

| Dimension | Weight | Key Indicators |
|-----------|--------|----------------|
| Technical | 25% | MACD, RSI(14+6), KDJ, MA(5/20/60/120), MA alignment |
| Capital | 30% | Volume ratio, turnover rate, bid-ask spread, volume direction |
| Fundamental | 10% | PE by industry (15 sectors), PB |
| Sentiment | 20% | 5-source news sentiment, market sentiment index |
| Market | 15% | HS300/CSI500/SSE50/ChiNext real-time |

### Anti-Momentum Mechanism

Prevents chasing highs and selling lows:

- **Momentum penalty**: Limit-up -12pts, big rise -6pts; Limit-down +8pts, big drop +4pts
- **RSI limits**: RSI>80 → signal capped at WATCH; RSI<20 → floor at WATCH
- **KDJ high blunting**: K>80 golden cross scores -1 instead of +4
- **Volume + direction**: High-volume surge -3pts (chasing risk), high-volume plunge -5pts (escape signal)
- **Consecutive trend penalty**: 3-day rally -5pts, 5-day rally -10pts
- **Northbound outflow**: 3-day consecutive outflow -4pts, 5-day -8pts

### Signal Levels

| Signal | Score Range | Action |
|--------|------------|--------|
| STRONG_BUY | ≥78 | Multi-dimension resonance, strong buy |
| BUY | ≥63 | Conditions met, suggest buy |
| WATCH | 40-63 | Monitor, no action |
| SELL | ≤22 | Deteriorating, consider sell |
| STRONG_SELL | <18 | Multi-dimension decline, strong sell |
| HOLD | Other | Maintain position |

## Data Source Architecture

### Fallback Chains

```
A-shares:    Tencent → Sina → EastMoney
US stocks:   Tencent US → yfinance
HK stocks:   Tencent HK
Commodities: Sina Commodity
Northbound:  EastMoney
Limit pool:  THS (Tonghuashun)
News:        EastMoney + Cailian Press + Jin10 + Sina 7x24 + WallStreetCN
LHB:         EastMoney (BILLBOARD API)
Margin:      EastMoney
Main flow:   EastMoney
```

### Anti-Ban Strategy

- Random delay (0.5-2s) + User-Agent rotation
- Circuit breaker: 5 consecutive failures → 60s pause → auto recovery
- Rate limit: ≤1 req/s per source

## Caching Architecture

| Layer | Storage | TTL | Purpose |
|-------|---------|-----|---------|
| SQLite | `stock_data/cache.db` | Daily refresh | 90-day K-lines for watchlist |
| JSON file | `cache/daily_market_log.json` | 60 days | Daily HS300 change + northbound flow |
| Memory | In-process dict | 60s | Market sentiment snapshot |
| Memory | In-process dict | 10min | HS300 consecutive up/down calculation |

## Cron Schedule (Trading Day)

| Time (CST) | Task | Timeout |
|------------|------|---------|
| 08:50 | K-line cache warm-up | 180s |
| 09:24-09:25 | Opening auction monitor | 180s |
| 09:30-14:30 (every 10min) | Watchlist monitor + anomaly detection | 180s |
| 14:50, 14:55 | Closing auction monitor | 180s |
| 15:05 | **Closing summary** (10-step analysis) | 360s |
| 21:30-05:00 (every 30min) | US stock snapshot | 180s |
| 05:30 | US market close summary | 360s |
| Saturday 10:00 | Weekly review | 360s |

## Project Structure

```
workspace-trading/
├── README.md                        # This file
├── SOUL.md                          # Agent identity & behavior rules
├── AGENTS.md                        # Multi-agent collaboration rules
├── mcp-server/                      # Quant Core (Python analysis library)
│   ├── data_sources/                # 8 data source adapters
│   │   ├── tencent.py / tencent_us.py / tencent_hk.py
│   │   ├── sina.py / sina_commodity.py / sina_market.py
│   │   ├── eastmoney.py / eastmoney_market.py / eastmoney_news.py
│   │   ├── ths.py / ths_market.py
│   │   ├── multi_news.py           # 5-source news aggregator
│   │   ├── manager.py              # Data source manager + K-line cache
│   │   └── base.py                 # Base class (fallback/circuit breaker)
│   ├── analysis/
│   │   ├── scoring.py              # Scoring V2 (5-dimension + anti-momentum)
│   │   ├── technical.py            # Technical indicator calculation
│   │   └── capital_flow.py         # Capital flow analysis
│   ├── utils/cache.py              # Cache system (KV + daily log + K-line)
│   ├── config/settings.yaml        # Weights, thresholds, watchlist
│   └── server.py                   # MCP Server (standby, not active)
├── skills/trading-quant/
│   ├── SKILL.md                    # Tool catalog & usage
│   └── scripts/quant.py            # CLI wrapper (exec entry point)
├── stock_data/
│   ├── cache.db                    # SQLite K-line cache
│   └── manager.py                  # StockDataManager
└── scripts/                        # Auxiliary scripts
```

## Getting Started

### Prerequisites

- Python 3.12+
- [OpenClaw CLI](https://github.com/openclaw) installed and configured
- A Discord bot token (for automated reports)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/lanyasheng/trading-system.git
cd trading-system

# 2. Install Python dependencies
cd mcp-server
uv sync  # or: pip install -r requirements.txt

# 3. Configure OpenClaw
openclaw init
# Edit ~/.openclaw/openclaw.json to add your model API keys and Discord token

# 4. Start the gateway
openclaw gateway install

# 5. Verify tools
./skills/trading-quant/scripts/quant.py system_health
./skills/trading-quant/scripts/quant.py stock_analysis
```

### Configuration

Edit `mcp-server/config/settings.yaml` to customize:

```yaml
watchlist:
  - {code: "002202", name: "Your Stock", market: "A"}

scoring:
  weights:
    technical: 0.25
    capital: 0.30
    fundamental: 0.10
    sentiment: 0.20
    market: 0.15
```

## Roadmap

- [ ] **Backtesting system**: Record predictions → compare T+1/3/5 results → accuracy stats → auto-tune weights
- [ ] **Portfolio tracking**: Virtual portfolio → returns vs HS300 benchmark → max drawdown / Sharpe ratio
- [ ] **Report archiving**: Store daily/weekly reports by date
- [ ] **Code convergence**: Unify quant.py and server.py into single entry point
- [ ] **X/Twitter monitoring**: Track key figures (policy makers, industry leaders)
- [ ] **Data quality SLI/SLO**: Source availability and latency P95 metrics
- [ ] **Multi-model A/B testing**: Compare scoring accuracy across different LLMs

## Disclaimer

This system is for **research and educational purposes only**. It does not constitute financial advice. Trading involves substantial risk. Always do your own research before making investment decisions.

## License

MIT
