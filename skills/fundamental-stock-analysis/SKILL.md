---
name: fundamental-stock-analysis
description: Fundamental equity analysis and peer ranking using a structured scoring playbook (quality, balance-sheet safety, cash flow, valuation, sector adjustments, confidence modifiers). Use when Nick asks to analyze one or more stock tickers, compare peers, choose a best pick, or produce a fundamentals-based verdict.
---

# fundamental-stock-analysis

1. Read `references/playbook.md` before starting analysis.
2. Follow the playbook steps exactly (input parse -> data collection -> quick screen -> scoring -> rating -> output).
3. For multi-ticker requests, analyze each ticker first, then rank peers and select best pick with invalidation triggers.
4. Always include confidence level and call out stale/conflicting data explicitly.
5. Append the required machine-readable JSON block at the end.

## Output discipline
- Keep conclusions decisive and risk-aware.
- Separate business quality, balance-sheet safety, and valuation.
- Never fabricate missing metrics; mark `NA`.
