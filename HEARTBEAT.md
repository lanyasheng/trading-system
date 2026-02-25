# HEARTBEAT.md - 交易蜘蛛心跳任务

## 交易时段检查（工作日 9:30-15:00）

当前是 A 股交易时段时，执行以下检查：

1. **自选股异动检测**
   - 运行 `uv run skills/a-stock-analysis/scripts/analyze.py 600519 000858 002594 002202`
   - 检查是否有涨跌幅超过 3% 的标的
   - 检查是否有分时放量异动（用 `--minute` 参数）

2. **推送条件**（满足任一则推送到 #trading 频道）
   - 自选股涨跌幅 > 3%
   - 大盘急跌 > 1.5%（上证/创业板）
   - 自选股出现主力大单异动

3. **推送格式**
   ```
   ⚡ 盘中异动 | HH:MM
   • [股票名] 涨/跌 X.XX%，原因:...
   ```

4. **不推送时**
   - 自选股波动正常（< 3%）
   - 大盘窄幅震荡
   - 回复 HEARTBEAT_OK

## 非交易时段

- 检查 `knowledge/` 目录是否需要整理
- 检查 MEMORY.md 是否需要更新
- 无事则 HEARTBEAT_OK

## 每日成本追踪（非交易时段执行，每天一次）

每天 21:00 左右执行一次:
1. 统计今日 session 数量: `ls /Users/study/.openclaw/agents/trading/sessions/*.jsonl | grep $(date +%Y-%m-%d) | wc -l`
2. 估算 token 消耗（基于 session 数量 × 平均 context）
3. 追加到 memory/YYYY-MM-DD.md:
   ```
   ## 📊 今日成本估算
   - Sessions: X 个
   - 估计 token: ~XX万 (基于平均每 session ~5k tokens)
   - Cron 任务: Y 次触发
   ```
4. 如果 sessions > 50（异常高）: 推送一条提醒
