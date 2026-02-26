# HEARTBEAT.md - 交易蜘蛛心跳任务

> 心跳任务现已通过 cron jobs 配置 (~/.openclaw/cron/jobs.json)，本文件仅作参考。

## 交易时段检查（工作日 9:30-15:00）

通过 cron 任务 `a-stock-watchlist-monitor`（每10分钟）自动执行:

```
quant.py stock_analysis → 检查异动 → 异动股调用 capital_flow → 推送到 #trading
```

**推送条件**（满足任一则推送）:
- 自选股涨跌幅 > 3%
- 评分 > 65 (BUY) 或 < 35 (SELL)
- 资金流异常

**不推送时**: 回复 HEARTBEAT_OK

## 全市场异动扫描

通过 cron 任务 `trading-market-scan`（每30分钟）:

```
quant.py market_scan → 全A涨跌幅/大额排行
```

## 非交易时段

- 检查 `knowledge/` 目录是否需要整理
- 检查 MEMORY.md 是否需要更新
- 无事则 HEARTBEAT_OK

## 工具调用

所有数据获取统一通过:
```
/Users/study/.openclaw/workspace-trading/mcp-server/.venv/bin/python3 \
  /Users/study/.openclaw/workspace-trading/skills/trading-quant/scripts/quant.py <tool> [args]
```

详见 `SOUL.md` 完整工具清单。
