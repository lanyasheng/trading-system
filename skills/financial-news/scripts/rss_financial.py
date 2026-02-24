#!/usr/bin/env python3
"""财经 RSS 聚合脚本 - 从 rss_sources.json 读取源"""

import json
import sys
import os
import xml.etree.ElementTree as ET
import urllib.request
from html import unescape
import re
from pathlib import Path


def load_sources(category=None):
    sources_file = Path(__file__).parent / "rss_sources.json"
    if not sources_file.exists():
        print(f"No sources file at {sources_file}", file=sys.stderr)
        return []
    with open(sources_file) as f:
        sources = json.load(f)
    if category and category != "all":
        sources = [s for s in sources if s.get("category") == category]
    return sources


def fetch_rss(url, timeout=12):
    proxy = None
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    if http_proxy:
        proxy = urllib.request.ProxyHandler({"http": http_proxy, "https": http_proxy})
    opener = urllib.request.build_opener(proxy) if proxy else urllib.request.build_opener()
    req = urllib.request.Request(url, headers={
        "User-Agent": "Trading-RSS-Aggregator/1.0",
        "Accept": "application/rss+xml, application/xml, text/xml",
    })
    try:
        resp = opener.open(req, timeout=timeout)
        return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def parse_rss(xml_content, source_name):
    items = []
    try:
        root = ET.fromstring(xml_content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            desc = unescape(re.sub(r"<[^>]+>", "", desc))[:300]
            items.append({"title": title, "url": link, "desc": desc, "date": pub_date, "source": source_name})
        for entry in root.findall("atom:entry", ns) + root.findall("entry"):
            title = ""
            t = entry.find("atom:title", ns) or entry.find("title")
            if t is not None and t.text: title = t.text.strip()
            link = ""
            l = entry.find("atom:link", ns) or entry.find("link")
            if l is not None: link = l.get("href", "").strip()
            desc = ""
            s = entry.find("atom:summary", ns) or entry.find("summary")
            if s is not None and s.text: desc = unescape(re.sub(r"<[^>]+>", "", s.text))[:300]
            pub_date = ""
            p = entry.find("atom:published", ns) or entry.find("published") or entry.find("atom:updated", ns) or entry.find("updated")
            if p is not None and p.text: pub_date = p.text.strip()
            items.append({"title": title, "url": link, "desc": desc, "date": pub_date, "source": source_name})
    except ET.ParseError:
        pass
    return items


def main():
    import argparse
    parser = argparse.ArgumentParser(description="财经 RSS 聚合")
    parser.add_argument("--category", default="all",
                       help="flash(快讯)/cn_deep(国内深度)/research(研报)/hk(港股)/intl(国际)/macro(宏观)")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--keyword", default=None, help="关键词筛选")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    sources = load_sources(args.category)
    all_items = []
    errors = []

    for src in sources:
        name = src["name"]
        print(f"  {name}...", file=sys.stderr, end="", flush=True)
        content = fetch_rss(src["url"])
        if content:
            items = parse_rss(content, name)
            all_items.extend(items[:args.limit])
            print(f" {len(items)}", file=sys.stderr)
        else:
            errors.append(name)
            print(f" FAIL", file=sys.stderr)

    if args.keyword:
        kws = [k.strip().lower() for k in args.keyword.split(",")]
        all_items = [i for i in all_items if any(kw in (i["title"] + i["desc"]).lower() for kw in kws)]

    if args.json:
        print(json.dumps(all_items, ensure_ascii=False, indent=2))
    else:
        cat_label = {"flash": "快讯", "cn_deep": "国内深度", "research": "研报",
                     "hk": "港股", "intl": "国际", "macro": "宏观", "all": "全部"}.get(args.category, args.category)
        print(f"\n📰 财经RSS [{cat_label}] - {len(all_items)} 条")
        if errors:
            print(f"⚠️ 失败: {', '.join(errors)}")
        print("=" * 60)
        for i, item in enumerate(all_items[:30], 1):
            print(f"\n{i}. [{item['source']}] {item['title']}")
            if item["date"]:
                print(f"   ⏰ {item['date'][:25]}")
            if item["desc"]:
                print(f"   {item['desc'][:120]}...")


if __name__ == "__main__":
    main()
