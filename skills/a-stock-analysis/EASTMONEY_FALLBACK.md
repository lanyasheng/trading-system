# Eastmoney Fallback Behavior

This repo now uses a resilient realtime quote strategy in `a-stock-analysis/scripts/analyze.py`:

1. Primary: Eastmoney `https://79.push2.eastmoney.com/api/qt/clist/get`
2. Fallback: Sina `https://hq.sinajs.cn/list=...`
3. Final fallback: Tencent `https://qt.gtimg.cn/q=...`

## Failure handling

- Network calls use retry + timeout and do not throw hard failures to caller.
- If one source fails or returns partial data, missing symbols are fetched from the next source.
- A single ticker failure does not terminate the full run; that ticker returns an error entry only.

## Diagnostics

Warnings are printed to `stderr` with:

- exception class
- endpoint host
- attempt count
- active fallback stage

Example warning format:

`[warn] fetch failed (1/3) host=79.push2.eastmoney.com error=RemoteDisconnected: Remote end closed connection without response`

## Knobs (current defaults)

- Realtime requests: `timeout=6~8s`, `retries=2~3`
- Backoff: linear sleep `0.3 * attempt` seconds
- Minute data (Sina): same retry wrapper, returns empty list on failure

These values are intentionally conservative for production safety and can be tuned in `_fetch_text_with_retry(...)`.
