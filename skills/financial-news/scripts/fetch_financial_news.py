#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["akshare>=1.16"]
# ///
"""
多源金融新闻聚合工具

数据源：
- 东方财富快讯
- 同花顺新闻
- 新浪财经要闻
- 宏观政策新闻

Usage:
    uv run fetch_financial_news.py                          # 全部新闻
    uv run fetch_financial_news.py --source eastmoney       # 东方财富
    uv run fetch_financial_news.py --source macro           # 宏观政策
    uv run fetch_financial_news.py --stock 600519           # 个股新闻
    uv run fetch_financial_news.py --keyword "降息"          # 关键词筛选
"""

import argparse
import json
import sys
from datetime import datetime


def fetch_eastmoney_news(limit=20):
    """东方财富全球财经快讯"""
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol="全球")
        items = []
        for _, row in df.head(limit).iterrows():
            items.append({
                "title": str(row.get("新闻标题", "")),
                "content": str(row.get("新闻内容", ""))[:200],
                "time": str(row.get("发布时间", "")),
                "source": "东方财富",
                "url": str(row.get("新闻链接", "")),
            })
        return items
    except Exception as e:
        print(f"东方财富新闻获取失败: {e}", file=sys.stderr)
        return []


def fetch_stock_news(stock_code, limit=10):
    """个股新闻"""
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=stock_code)
        items = []
        for _, row in df.head(limit).iterrows():
            items.append({
                "title": str(row.get("新闻标题", "")),
                "content": str(row.get("新闻内容", ""))[:200],
                "time": str(row.get("发布时间", "")),
                "source": f"东方财富-{stock_code}",
                "url": str(row.get("新闻链接", "")),
            })
        return items
    except Exception as e:
        print(f"个股新闻获取失败: {e}", file=sys.stderr)
        return []


def fetch_cctv_news(limit=10):
    """CCTV 新闻联播要点（重大政策信号）"""
    try:
        import akshare as ak
        df = ak.news_cctv(date=datetime.now().strftime("%Y%m%d"))
        items = []
        for _, row in df.head(limit).iterrows():
            items.append({
                "title": str(row.get("title", "")),
                "content": str(row.get("content", ""))[:200],
                "time": datetime.now().strftime("%Y-%m-%d"),
                "source": "新闻联播",
            })
        return items
    except Exception as e:
        print(f"CCTV 新闻获取失败: {e}", file=sys.stderr)
        return []


def fetch_macro_data():
    """宏观经济数据概览"""
    try:
        import akshare as ak
        result = {}

        try:
            cpi = ak.macro_china_cpi_monthly()
            if not cpi.empty:
                latest = cpi.iloc[-1]
                result["CPI"] = str(latest.iloc[-1])
        except Exception:
            pass

        try:
            pmi = ak.macro_china_pmi()
            if not pmi.empty:
                latest = pmi.iloc[-1]
                result["PMI"] = str(latest.iloc[-1])
        except Exception:
            pass

        return result
    except Exception as e:
        print(f"宏观数据获取失败: {e}", file=sys.stderr)
        return {}


def fetch_market_sentiment():
    """市场情绪指标"""
    try:
        import akshare as ak
        result = {}

        try:
            north = ak.stock_hsgt_north_net_flow_in_em(symbol="沪股通")
            if not north.empty:
                latest = north.iloc[-1]
                result["北向资金净流入"] = str(latest.get("净流入", ""))
        except Exception:
            pass

        try:
            margin = ak.stock_margin_sse(start_date=datetime.now().strftime("%Y%m%d"))
            if not margin.empty:
                latest = margin.iloc[-1]
                result["融资余额"] = str(latest.get("融资余额", ""))
        except Exception:
            pass

        return result
    except Exception as e:
        print(f"市场情绪获取失败: {e}", file=sys.stderr)
        return {}


def filter_by_keyword(items, keywords):
    """按关键词筛选新闻"""
    if not keywords:
        return items
    kw_list = [k.strip().lower() for k in keywords.split(",")]
    filtered = []
    for item in items:
        text = (item.get("title", "") + item.get("content", "")).lower()
        if any(kw in text for kw in kw_list):
            filtered.append(item)
    return filtered


def main():
    parser = argparse.ArgumentParser(description="金融新闻聚合")
    parser.add_argument("--source", default="all",
                       choices=["all", "eastmoney", "cctv", "macro", "sentiment"],
                       help="新闻源")
    parser.add_argument("--stock", default=None, help="个股代码")
    parser.add_argument("--keyword", default=None, help="关键词筛选（逗号分隔）")
    parser.add_argument("--limit", type=int, default=15, help="每源最大条目")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    all_items = []

    if args.stock:
        items = fetch_stock_news(args.stock, args.limit)
        all_items.extend(items)
    else:
        if args.source in ("all", "eastmoney"):
            items = fetch_eastmoney_news(args.limit)
            all_items.extend(items)
            print(f"  东方财富: {len(items)} 条", file=sys.stderr)

        if args.source in ("all", "cctv"):
            items = fetch_cctv_news(args.limit)
            all_items.extend(items)
            print(f"  新闻联播: {len(items)} 条", file=sys.stderr)

    if args.keyword:
        all_items = filter_by_keyword(all_items, args.keyword)
        print(f"  关键词筛选后: {len(all_items)} 条", file=sys.stderr)

    extra = {}
    if args.source in ("all", "macro"):
        extra["macro"] = fetch_macro_data()
    if args.source in ("all", "sentiment"):
        extra["sentiment"] = fetch_market_sentiment()

    if args.json:
        output = {"news": all_items, "extra": extra}
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"\n📰 金融新闻聚合 - 共 {len(all_items)} 条")
        print("=" * 60)

        for i, item in enumerate(all_items[:20], 1):
            src = item.get("source", "")
            time_str = item.get("time", "")
            print(f"\n{i}. [{src}] {item['title']}")
            if time_str:
                print(f"   ⏰ {time_str}")
            if item.get("content"):
                print(f"   {item['content'][:100]}...")

        if extra.get("macro"):
            print(f"\n📊 宏观数据")
            for k, v in extra["macro"].items():
                print(f"  • {k}: {v}")

        if extra.get("sentiment"):
            print(f"\n💹 市场情绪")
            for k, v in extra["sentiment"].items():
                print(f"  • {k}: {v}")


if __name__ == "__main__":
    main()
