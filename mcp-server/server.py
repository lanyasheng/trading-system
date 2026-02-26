"""Trading Quant MCP Server — quantitative analysis tools for OpenClaw Trading Spider.

Run: uv run mcp-server/server.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_ws = Path(__file__).resolve().parent.parent
if str(_ws) not in sys.path:
    sys.path.insert(0, str(_ws))

from mcp.server.fastmcp import FastMCP

from data_sources.manager import DataManager
from analysis.scoring import compute_stock_score, StockScore
from config import get_config

# Global market data sources
from data_sources.tencent_hk import TencentHKRealtimeSource
from data_sources.sina_commodity import SinaCommoditySource, COMMODITY_MAP
from data_sources.tencent_us import TencentUSRealtimeSource
from data_sources.ths_market import THSMarketScanner
from data_sources.eastmoney_northbound import NorthboundFlowSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("trading-quant")

mcp = FastMCP(
    "trading-quant",
    instructions="全球市场量化分析MCP服务器 - A股/美股/港股/贵金属/原油多维评分",
)

_data_mgr: DataManager | None = None


def _get_data_manager() -> DataManager:
    global _data_mgr
    if _data_mgr is None:
        _data_mgr = DataManager()
    return _data_mgr


def _load_watchlist() -> dict:
    """Load watchlist from knowledge/watchlist.json.

    Returns flat code lists, handling both string and object formats.
    """
    ws = Path(__file__).resolve().parent.parent
    wl_path = ws / "knowledge" / "watchlist.json"
    if not wl_path.exists():
        return {"priority": [], "observe": [], "research": []}

    with open(wl_path, "r") as f:
        raw = json.load(f)

    result = {}
    for key in ("priority", "observe", "research"):
        items = raw.get(key, [])
        codes = []
        for item in items:
            if isinstance(item, dict):
                codes.append(item.get("code", ""))
            else:
                codes.append(str(item))
        result[key] = [c for c in codes if c]
    return result


def _clean_code(code: str) -> str:
    return code.replace(".", "").replace("sh", "").replace("sz", "").strip()


@mcp.tool()
async def get_stock_analysis(codes: str = "") -> str:
    """获取股票多维度量化分析。

    输入: codes - 逗号分隔的股票代码(如 "600519,000858")。为空则分析全部自选股。
    输出: JSON格式的多维评分结果(技术面30%+资金面35%+消息面20%+市场情绪15%)。
    每只股票包含总评分(0-100)、信号等级、各维度评分和信号说明、风险提示。
    """
    dm = _get_data_manager()

    if codes.strip():
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
    else:
        wl = _load_watchlist()
        code_list = wl.get("priority", []) + wl.get("observe", [])

    if not code_list:
        return json.dumps({"error": "无股票代码，请提供codes参数或配置watchlist.json"}, ensure_ascii=False)

    quotes = await dm.get_realtime_quotes(code_list)
    quote_map = {q.code: q for q in quotes}

    results = []
    for code in code_list:
        cc = _clean_code(code)
        if len(cc) != 6:
            continue
        quote = quote_map.get(cc)
        if not quote:
            results.append({"code": cc, "error": "实时行情获取失败"})
            continue

        daily_df = dm.get_daily_klines(cc, days=60)
        avg_volume = 0.0
        avg_amount = 0.0
        if daily_df is not None and len(daily_df) >= 5:
            avg_volume = float(daily_df["volume"].tail(5).mean())
            if "amount" in daily_df.columns:
                avg_amount = float(daily_df["amount"].tail(5).mean())

        score = compute_stock_score(
            quote=quote, daily_df=daily_df,
            avg_volume=avg_volume, avg_amount=avg_amount,
        )
        results.append(score.to_dict())

    summary = _build_summary(results)
    return json.dumps(
        {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "stocks": results, "summary": summary},
        ensure_ascii=False, indent=2,
    )


@mcp.tool()
async def get_morning_brief() -> str:
    """获取盘前晨报数据包。

    输出: JSON格式包含自选股评分概览、前日收盘回顾、今日关注重点。
    LLM 直接基于此生成晨报。
    """
    dm = _get_data_manager()
    wl = _load_watchlist()
    all_codes = wl.get("priority", []) + wl.get("observe", [])

    brief = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "morning_brief",
        "watchlist_count": len(all_codes),
        "previous_close": [],
        "focus_today": [],
    }

    if not all_codes:
        brief["note"] = "自选股列表为空"
        return json.dumps(brief, ensure_ascii=False, indent=2)

    for code in all_codes:
        cc = _clean_code(code)
        if len(cc) != 6:
            continue
        daily_df = dm.get_daily_klines(cc, days=10)
        if daily_df is None or daily_df.empty:
            continue

        last = daily_df.iloc[-1]
        prev = daily_df.iloc[-2] if len(daily_df) >= 2 else last
        change = round((float(last["close"]) - float(prev["close"])) / float(prev["close"]) * 100, 2)

        entry = {
            "code": cc,
            "close": float(last["close"]),
            "change_pct": change,
            "volume": float(last["volume"]),
        }
        brief["previous_close"].append(entry)

        if abs(change) > 3:
            direction = "大涨" if change > 0 else "大跌"
            brief["focus_today"].append({
                "code": cc,
                "reason": "前日" + direction + str(round(change, 1)) + "%",
                "suggestion": "关注开盘走势" if change > 0 else "关注是否企稳",
            })

    hour_now = datetime.now().hour
    if hour_now < 9:
        brief["market_status"] = "盘前"
    elif hour_now < 15:
        brief["market_status"] = "已开盘"
    else:
        brief["market_status"] = "已收盘"

    return json.dumps(brief, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_closing_summary() -> str:
    """获取收盘复盘数据包。

    输出: JSON格式包含自选股全量评分、涨跌排行、信号汇总、风险提示。
    LLM 直接基于此生成收盘复盘报告。
    """
    dm = _get_data_manager()
    wl = _load_watchlist()
    all_codes = wl.get("priority", []) + wl.get("observe", [])

    summary_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "closing_summary",
        "stocks": [],
        "top_gainers": [],
        "top_losers": [],
        "strong_signals": [],
        "risk_alerts": [],
    }

    if not all_codes:
        summary_data["note"] = "自选股列表为空"
        return json.dumps(summary_data, ensure_ascii=False, indent=2)

    quotes = await dm.get_realtime_quotes(all_codes)
    quote_map = {q.code: q for q in quotes}

    scored: list[dict] = []
    for code in all_codes:
        cc = _clean_code(code)
        if len(cc) != 6:
            continue
        quote = quote_map.get(cc)
        if not quote:
            continue

        daily_df = dm.get_daily_klines(cc, days=60)
        avg_volume = 0.0
        avg_amount = 0.0
        if daily_df is not None and len(daily_df) >= 5:
            avg_volume = float(daily_df["volume"].tail(5).mean())
            if "amount" in daily_df.columns:
                avg_amount = float(daily_df["amount"].tail(5).mean())

        score = compute_stock_score(
            quote=quote, daily_df=daily_df,
            avg_volume=avg_volume, avg_amount=avg_amount,
        )
        d = score.to_dict()
        scored.append(d)

        if score.signal in ("STRONG_BUY", "BUY"):
            summary_data["strong_signals"].append({
                "code": score.code, "name": score.name,
                "signal": score.signal, "score": score.total_score,
            })
        if score.risk_alerts:
            for a in score.risk_alerts:
                summary_data["risk_alerts"].append({"code": score.code, "alert": a})

    scored.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    summary_data["stocks"] = scored
    summary_data["top_gainers"] = scored[:3] if scored else []
    summary_data["top_losers"] = scored[-3:][::-1] if len(scored) >= 3 else []

    return json.dumps(summary_data, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_system_health() -> str:
    """获取MCP Server健康状态和数据源状态。

    输出: JSON格式包含数据源可用性、缓存命中率、熔断器状态。
    """
    dm = _get_data_manager()
    return json.dumps(dm.health_report(), ensure_ascii=False, indent=2)




@mcp.tool()
async def warm_klines(days: int = 90) -> str:
    """预热全部自选股的历史K线数据。

    从数据源拉取最近N天的日K线数据并缓存到SQLite。
    建议每日盘前运行一次(7:00)确保数据充足。
    """
    dm = _get_data_manager()
    wl = _load_watchlist()
    all_codes = wl.get("priority", []) + wl.get("observe", []) + wl.get("research", [])
    all_codes = [_clean_code(c) for c in all_codes if len(_clean_code(c)) == 6]

    result = dm.warm_klines(all_codes, days=days)
    return json.dumps(result, ensure_ascii=False, indent=2)




# === Global Market Data ===

_us_data_mgr = None
_hk_source = None
_commodity_source = None
_us_tencent_source = None
_market_scanner = None
_northbound_source = None


def _get_us_data_manager():
    global _us_data_mgr
    if _us_data_mgr is None:
        try:
            from us_data import USDataManager
            _us_data_mgr = USDataManager()
        except Exception as e:
            logger.warning(f"US data manager init failed: {e}")
    return _us_data_mgr


def _get_hk_source():
    global _hk_source
    if _hk_source is None:
        _hk_source = TencentHKRealtimeSource()
    return _hk_source


def _get_northbound_source():
    global _northbound_source
    if _northbound_source is None:
        _northbound_source = NorthboundFlowSource()
    return _northbound_source


def _get_market_scanner():
    global _market_scanner
    if _market_scanner is None:
        _market_scanner = THSMarketScanner()
    return _market_scanner


def _get_us_tencent_source():
    global _us_tencent_source
    if _us_tencent_source is None:
        _us_tencent_source = TencentUSRealtimeSource()
    return _us_tencent_source


def _get_commodity_source():
    global _commodity_source
    if _commodity_source is None:
        _commodity_source = SinaCommoditySource()
    return _commodity_source


def _load_global_watchlist() -> dict:
    """Load global watchlist (US/HK/commodity) from watchlist.json."""
    ws = Path(__file__).resolve().parent.parent
    wl_path = ws / "knowledge" / "watchlist.json"
    if not wl_path.exists():
        return {"us": [], "hk": [], "commodity": []}

    with open(wl_path, "r") as f:
        raw = json.load(f)

    result = {}
    for key in ("us", "hk", "commodity"):
        items = raw.get(key, [])
        codes = []
        for item in items:
            if isinstance(item, dict):
                codes.append(item.get("code", item.get("symbol", "")))
            else:
                codes.append(str(item))
        result[key] = [c for c in codes if c]
    return result


@mcp.tool()
async def get_us_stock_analysis(symbols: str = "") -> str:
    """获取美股实时行情与分析。

    输入: symbols - 逗号分隔的美股代码(如 "AAPL,TSLA,NVDA")。为空则分析全部美股自选。
    输出: JSON格式包含每只股票的价格、涨跌幅。数据源优先级: 腾讯(快) > yfinance(降级)。
    """
    if symbols.strip():
        sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        wl = _load_global_watchlist()
        sym_list = wl.get("us", [])

    if not sym_list:
        return json.dumps({"error": "无美股代码，请提供symbols参数或在watchlist.json添加us列表"}, ensure_ascii=False)

    stocks = []
    source_used = "none"

    # Primary: Tencent (fast, no rate limit)
    try:
        tencent = _get_us_tencent_source()
        quotes = await tencent.fetch_quotes(sym_list)
        source_used = "tencent"
        for q in quotes:
            if q:
                stocks.append({
                    "symbol": q.code, "name": q.name, "price": q.price,
                    "prev_close": q.pre_close, "change_pct": q.change_pct,
                    "high": q.high, "low": q.low, "source": "tencent", "status": "ok",
                })
            else:
                stocks.append({"symbol": "?", "source": "tencent", "status": "error"})
    except Exception as e:
        logger.warning(f"Tencent US failed: {e}, falling back to yfinance")

    # Fallback: yfinance (if Tencent failed or returned no data)
    ok_symbols = {s["symbol"] for s in stocks if s.get("status") == "ok"}
    missing = [s for s in sym_list if s not in ok_symbols]
    if missing:
        try:
            us_mgr = _get_us_data_manager()
            if us_mgr:
                df = us_mgr.get_snapshots(missing)
                source_used = "tencent+yfinance" if ok_symbols else "yfinance"
                for _, row in df.iterrows():
                    stocks.append({
                        "symbol": row["symbol"],
                        "price": round(float(row["last"]), 2) if row["last"] is not None else None,
                        "prev_close": round(float(row["prev"]), 2) if row["prev"] is not None else None,
                        "change_pct": round(float(row["pct"]), 2) if row["pct"] is not None else None,
                        "source": row.get("source", "yfinance"),
                        "status": row.get("status", "unknown"),
                    })
        except Exception as e:
            logger.warning(f"yfinance fallback also failed: {e}")

    return json.dumps({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "us_stock_analysis",
        "count": len(stocks),
        "source": source_used,
        "stocks": stocks,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_hk_stock_analysis(codes: str = "") -> str:
    """获取港股实时行情。

    输入: codes - 逗号分隔的港股代码(如 "00700,09988,03690")。为空则分析全部港股自选。
    输出: JSON格式包含每只股票的价格、涨跌幅。
    """
    hk = _get_hk_source()

    if codes.strip():
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
    else:
        wl = _load_global_watchlist()
        code_list = wl.get("hk", [])

    if not code_list:
        return json.dumps({"error": "无港股代码，请提供codes参数或在watchlist.json添加hk列表"}, ensure_ascii=False)

    try:
        quotes = await hk.fetch_quotes(code_list)
        stocks = []
        for q in quotes:
            if q:
                stocks.append({
                    "code": q.code,
                    "name": q.name,
                    "price": q.price,
                    "prev_close": q.prev_close,
                    "change_pct": q.change_pct,
                    "high": q.high,
                    "low": q.low,
                    "volume": q.volume,
                    "turnover_rate": q.turnover_rate,
                })
            else:
                stocks.append({"code": "unknown", "error": "数据获取失败"})
        return json.dumps({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "hk_stock_analysis",
            "count": len(stocks),
            "stocks": stocks,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"港股数据获取失败: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
async def get_commodity_analysis(codes: str = "") -> str:
    """获取贵金属和原油实时行情。

    输入: codes - 逗号分隔的商品代码。可选: XAU(COMEX黄金),XAG(COMEX白银),WTI(WTI原油),BRENT(布伦特原油),GOLD_CN(沪金),SILVER_CN(沪银),CRUDE_CN(原油期货)。
    为空则分析全部商品自选。
    输出: JSON格式包含价格、涨跌幅。
    """
    source = _get_commodity_source()

    if codes.strip():
        code_list = [c.strip().upper() for c in codes.split(",") if c.strip()]
    else:
        wl = _load_global_watchlist()
        code_list = wl.get("commodity", [])

    if not code_list:
        code_list = list(COMMODITY_MAP.keys())

    try:
        quotes = await source.fetch_quotes(code_list)
        commodities = []
        for q in quotes:
            if q:
                commodities.append({
                    "code": q.code,
                    "name": q.name,
                    "price": q.price,
                    "prev_close": q.prev_close,
                    "change_pct": q.change_pct,
                    "high": q.high,
                    "low": q.low,
                })
            else:
                commodities.append({"code": "unknown", "error": "数据获取失败"})
        return json.dumps({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "commodity_analysis",
            "count": len(commodities),
            "commodities": commodities,
            "available_codes": list(COMMODITY_MAP.keys()),
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"商品数据获取失败: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
async def get_global_overview() -> str:
    """获取全球市场概览 — A股+美股+港股+贵金属+原油。

    一次调用获取所有市场自选股的实时行情汇总。
    输出: JSON格式包含各市场的价格和涨跌数据。
    """
    overview = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "global_overview",
        "markets": {},
    }

    # A-shares
    try:
        dm = _get_data_manager()
        wl = _load_watchlist()
        a_codes = wl.get("priority", []) + wl.get("observe", [])
        if a_codes:
            a_quotes = await dm.get_realtime_quotes(a_codes[:10])
            overview["markets"]["a_shares"] = {
                "count": len(a_quotes),
                "stocks": [
                    {"code": q.code, "name": q.name, "price": q.price, "change_pct": q.change_pct}
                    for q in a_quotes if q
                ],
            }
    except Exception as e:
        overview["markets"]["a_shares"] = {"error": str(e)}

    # US stocks (Tencent primary)
    try:
        wl_global = _load_global_watchlist()
        us_syms = wl_global.get("us", [])
        if us_syms:
            tencent_us = _get_us_tencent_source()
            us_quotes = await tencent_us.fetch_quotes(us_syms)
            overview["markets"]["us_stocks"] = {
                "count": len([q for q in us_quotes if q]),
                "stocks": [
                    {"symbol": q.code, "name": q.name, "price": q.price, "change_pct": q.change_pct}
                    for q in us_quotes if q
                ],
            }
    except Exception as e:
        overview["markets"]["us_stocks"] = {"error": str(e)}

    # HK stocks
    try:
        hk = _get_hk_source()
        if "wl_global" not in dir():
            wl_global = _load_global_watchlist()
        hk_codes = wl_global.get("hk", [])
        if hk_codes:
            hk_quotes = await hk.fetch_quotes(hk_codes)
            overview["markets"]["hk_stocks"] = {
                "count": len(hk_quotes),
                "stocks": [
                    {"code": q.code, "name": q.name, "price": q.price, "change_pct": q.change_pct}
                    for q in hk_quotes if q
                ],
            }
    except Exception as e:
        overview["markets"]["hk_stocks"] = {"error": str(e)}

    # Commodities
    try:
        com = _get_commodity_source()
        com_codes = _load_global_watchlist().get("commodity", list(COMMODITY_MAP.keys()))
        if com_codes:
            com_quotes = await com.fetch_quotes(com_codes)
            overview["markets"]["commodities"] = {
                "count": len(com_quotes),
                "items": [
                    {"code": q.code, "name": q.name, "price": q.price, "change_pct": q.change_pct}
                    for q in com_quotes if q
                ],
            }
    except Exception as e:
        overview["markets"]["commodities"] = {"error": str(e)}

    return json.dumps(overview, ensure_ascii=False, indent=2)




@mcp.tool()
async def get_market_anomaly() -> str:
    """获取A股市场异动扫描 — 涨停池/跌停池/炸板池。

    输出: JSON格式包含今日涨停/跌停/炸板股票列表，含首板/连板/回封标签。
    用于发现市场热点和异动信号。
    """
    scanner = _get_market_scanner()
    result = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "market_anomaly",
    }

    try:
        limit_up = await scanner.get_limit_up_pool()
        result["limit_up"] = limit_up

        first_limit = [s for s in limit_up.get("stocks", []) if s.get("change_tag") == "FIRST_LIMIT"]
        again_limit = [s for s in limit_up.get("stocks", []) if s.get("is_again_limit")]
        result["summary"] = {
            "total_limit_up": limit_up.get("total", 0),
            "first_limit_count": len(first_limit),
            "again_limit_count": len(again_limit),
        }
    except Exception as e:
        result["limit_up"] = {"error": str(e)}

    try:
        limit_down = await scanner.get_limit_down_pool()
        result["limit_down"] = limit_down
        if "summary" not in result:
            result["summary"] = {}
        result["summary"]["total_limit_down"] = limit_down.get("total", 0)
    except Exception as e:
        result["limit_down"] = {"error": str(e)}

    try:
        fried = await scanner.get_fried_plate_pool()
        result["fried_plate"] = fried
        if "summary" not in result:
            result["summary"] = {}
        result["summary"]["total_fried"] = fried.get("total", 0)
    except Exception as e:
        result["fried_plate"] = {"error": str(e)}

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_capital_flow(codes: str = "") -> str:
    """获取个股分钟级资金流数据。

    输入: codes - 逗号分隔的A股代码(如 "600519,000858")。为空则获取全部自选股。
    输出: JSON格式包含每只股票的分钟级资金流入/流出、近10分钟是否放量异常。
    """
    scanner = _get_market_scanner()

    if codes.strip():
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
    else:
        wl = _load_watchlist()
        code_list = (wl.get("priority", []) + wl.get("observe", []))[:10]

    if not code_list:
        return json.dumps({"error": "无股票代码"}, ensure_ascii=False)

    results = []
    for code in code_list:
        cc = _clean_code(code)
        if len(cc) != 6:
            continue
        try:
            flow = await scanner.get_capital_flow(cc)
            results.append(flow)
        except Exception as e:
            results.append({"code": cc, "error": str(e)})

    surging = [r for r in results if r.get("amount_surge_last_10min")]

    return json.dumps({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "capital_flow",
        "count": len(results),
        "stocks": results,
        "alert": {
            "surging_count": len(surging),
            "surging_codes": [r["code"] for r in surging],
        } if surging else None,
    }, ensure_ascii=False, indent=2)




@mcp.tool()
async def get_northbound_flow() -> str:
    """获取北向资金(沪深港通)实时流入/流出数据。

    输出: JSON格式包含沪股通/深股通净流入额(亿元)、市场情绪判断。
    北向资金是A股最重要的情绪指标之一。净流入>5亿看多，净流出>5亿看空。
    """
    source = _get_northbound_source()
    try:
        flow = await source.get_realtime_flow()
        return json.dumps({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "northbound_flow",
            "flow": flow,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"北向资金数据获取失败: {str(e)}"}, ensure_ascii=False)


def _build_summary(results: list[dict]) -> dict:
    """Build aggregated summary from individual stock scores."""
    valid = [r for r in results if "error" not in r]
    if not valid:
        return {"total_stocks": 0, "note": "无有效数据"}

    scores = [r["score"]["total"] for r in valid]
    signals = {}
    for r in valid:
        sig = r.get("signal", "UNKNOWN")
        signals[sig] = signals.get(sig, 0) + 1

    best = max(valid, key=lambda x: x["score"]["total"])
    worst = min(valid, key=lambda x: x["score"]["total"])

    return {
        "total_stocks": len(valid),
        "avg_score": round(sum(scores) / len(scores), 1),
        "max_score": {"code": best["code"], "score": max(scores)},
        "min_score": {"code": worst["code"], "score": min(scores)},
        "signal_distribution": signals,
    }


if __name__ == "__main__":
    mcp.run()
