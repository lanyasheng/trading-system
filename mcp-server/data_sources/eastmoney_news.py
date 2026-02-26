"""东方财富新闻/快讯抓取 + 基于关键词的情绪评分."""

from __future__ import annotations
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://finance.eastmoney.com",
}

BULLISH_KEYWORDS = [
    "利好", "上涨", "大涨", "涨停", "突破", "新高", "增长", "超预期",
    "加仓", "买入", "增持", "回购", "分红", "提高", "超额", "盈利",
    "景气", "复苏", "反弹", "放量", "主力", "净流入", "抄底",
    "刺激", "降息", "降准", "宽松", "扩大", "加速", "强势",
    "签约", "中标", "订单", "创新", "突破性", "营收增长", "利润增长",
]
BEARISH_KEYWORDS = [
    "利空", "下跌", "大跌", "跌停", "破位", "新低", "下滑", "不及预期",
    "减仓", "卖出", "减持", "质押", "亏损", "下调", "低于", "萎缩",
    "疲软", "衰退", "暴跌", "缩量", "抛售", "净流出", "割肉",
    "制裁", "加息", "收紧", "紧缩", "风险", "警告", "恐慌",
    "违规", "处罚", "退市", "ST", "问询", "立案", "调查",
]


@dataclass
class NewsItem:
    title: str
    time: str
    source: str
    url: str = ""
    sentiment: float = 0.0
    keywords: list[str] = field(default_factory=list)


class EastMoneyNewsFetcher:
    """东方财富快讯和个股新闻."""

    KUAIXUN_API = "https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_{limit}_{page}_.html"

    async def get_market_news(self, limit: int = 30) -> list[NewsItem]:
        """获取财经快讯(7x24)."""
        url = self.KUAIXUN_API.format(limit=limit, page=1)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=HEADERS)
                resp.raise_for_status()
                text = resp.text

            json_match = re.search(r"var ajaxResult=(\{.*\})", text, re.DOTALL)
            if not json_match:
                logger.warning("EastMoney kuaixun: no JSON in response")
                return []

            data = json.loads(json_match.group(1))
            items = []
            for n in data.get("LivesList", []):
                title = n.get("title", "") or n.get("digest", "")
                if not title:
                    continue
                pub_time = n.get("showtime", "")
                source = n.get("source", "东方财富")
                news_url = n.get("url_w", "")
                sentiment, kw = self._score_sentiment(title)
                digest = n.get("digest", "")
                if digest and digest != title:
                    s2, kw2 = self._score_sentiment(digest)
                    sentiment = round((sentiment + s2) / 2, 1)
                    kw.extend(kw2)
                items.append(NewsItem(
                    title=title, time=pub_time, source=source,
                    url=news_url, sentiment=sentiment, keywords=list(set(kw)),
                ))
            return items
        except Exception as e:
            logger.warning("EastMoney market news failed: %s", e)
            return []

    async def get_stock_news(self, code: str, name: str = "", limit: int = 10) -> list[NewsItem]:
        """获取个股相关新闻(东方财富搜索)."""
        search_term = name or code
        url = "https://search-api-web.eastmoney.com/search/jsonp"
        cb = "jQuery_news_%d" % int(time.time() * 1000)
        search_params = {
            "cb": cb,
            "param": json.dumps({
                "uid": "",
                "keyword": search_term,
                "type": ["cmsArticleWebOld"],
                "client": "web",
                "clientType": "web",
                "clientVersion": "curr",
                "param": {
                    "cmsArticleWebOld": {
                        "searchScope": "default",
                        "sort": "default",
                        "pageIndex": 1,
                        "pageSize": limit,
                    }
                }
            }),
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=search_params, headers=HEADERS)
                resp.raise_for_status()
                text = resp.text

            json_match = re.search(cb + r"\((.*)\)", text, re.DOTALL)
            if not json_match:
                return []
            data = json.loads(json_match.group(1))

            items = []
            article_data = data.get("result", {})
            if isinstance(article_data, dict):
                results = article_data.get("cmsArticleWebOld", {})
                if isinstance(results, dict):
                    result_list = results.get("list", [])
                elif isinstance(results, list):
                    result_list = results
                else:
                    result_list = []
            else:
                result_list = []

            for r in result_list:
                if not isinstance(r, dict):
                    continue
                title = r.get("title", "").replace("<em>", "").replace("</em>", "")
                pub_time = r.get("date", "")
                source = r.get("mediaName", "")
                news_url = r.get("url", "")
                sentiment, kw = self._score_sentiment(title)
                content = r.get("content", "")
                if content:
                    s2, kw2 = self._score_sentiment(content[:200])
                    sentiment = round((sentiment + s2) / 2, 1)
                    kw.extend(kw2)
                items.append(NewsItem(
                    title=title, time=pub_time, source=source,
                    url=news_url, sentiment=sentiment, keywords=list(set(kw)),
                ))
            return items
        except Exception as e:
            logger.warning("EastMoney stock news for %s failed: %s", code, e)
            return []

    NEGATIVE_CONTEXT = ["跌幅", "降幅", "亏损", "收窄", "减少"]

    def _score_sentiment(self, text: str) -> tuple[float, list[str]]:
        """基于关键词的简单情绪评分 (-5 to +5)."""
        score = 0.0
        matched = []
        for kw in BULLISH_KEYWORDS:
            if kw in text:
                # Check if this bullish word appears in a negative context
                neg_context = any(neg + kw in text or kw + neg in text for neg in self.NEGATIVE_CONTEXT)
                if neg_context:
                    score -= 0.5
                    matched.append(f"~{kw}(反向)")
                else:
                    score += 1.0
                    matched.append(f"+{kw}")
        for kw in BEARISH_KEYWORDS:
            if kw in text:
                score -= 1.0
                matched.append(f"-{kw}")
        score = max(-5.0, min(5.0, score))
        return round(score, 1), matched


async def get_market_sentiment_from_news(limit: int = 20) -> dict:
    """获取市场情绪汇总."""
    fetcher = EastMoneyNewsFetcher()
    news = await fetcher.get_market_news(limit=limit)
    if not news:
        return {"sentiment": "neutral", "score": 0, "news_count": 0, "headlines": []}

    avg_score = sum(n.sentiment for n in news) / len(news) if news else 0
    bullish = sum(1 for n in news if n.sentiment > 0)
    bearish = sum(1 for n in news if n.sentiment < 0)
    neutral = sum(1 for n in news if n.sentiment == 0)

    if avg_score > 0.5:
        sentiment = "bullish"
    elif avg_score < -0.5:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    top_headlines = []
    for n in sorted(news, key=lambda x: abs(x.sentiment), reverse=True)[:5]:
        top_headlines.append({
            "title": n.title,
            "sentiment": n.sentiment,
            "time": n.time,
            "keywords": n.keywords[:3],
        })

    return {
        "sentiment": sentiment,
        "score": round(avg_score, 2),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "news_count": len(news),
        "top_headlines": top_headlines,
    }
