"""东方财富北向资金(沪深港通)实时数据."""

from __future__ import annotations
import re
import json
import logging
import httpx

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://data.eastmoney.com",
}


class NorthboundFlowSource:
    """东方财富北向资金实时流入/流出数据."""

    URL = "https://push2.eastmoney.com/api/qt/kamt.rtmin/get"

    async def get_realtime_flow(self) -> dict:
        """获取今日北向资金分钟级流入数据."""
        params = {
            "fields1": "f1,f2,f3,f4",
            "fields2": "f51,f52,f53,f54,f55,f56",
        }
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            resp = await client.get(self.URL, params=params)
            resp.raise_for_status()
            text = resp.text

        m = re.search(r'\{.*\}', text, re.DOTALL)
        if not m:
            return {"error": "parse failed"}

        data = json.loads(m.group(0))
        if data.get("rc") != 0:
            return {"error": "API error", "rc": data.get("rc")}

        s2n = data.get("data", {}).get("s2n", [])
        if not s2n:
            return {"note": "no data (non-trading hours or holiday)"}

        flow_points = []
        for point in s2n:
            parts = point.split(",")
            if len(parts) >= 6:
                time_str = parts[0]
                sh_net = float(parts[1]) if parts[1] else 0
                sh_buy = float(parts[2]) if parts[2] else 0
                sz_net = float(parts[3]) if parts[3] else 0
                sz_buy = float(parts[4]) if parts[4] else 0
                total_net = float(parts[5]) if parts[5] else 0
                flow_points.append({
                    "time": time_str,
                    "sh_net": sh_net,
                    "sz_net": sz_net,
                    "total_net": total_net,
                })

        last = flow_points[-1] if flow_points else {}
        total_net = last.get("total_net", 0)
        sh_net = last.get("sh_net", 0)
        sz_net = last.get("sz_net", 0)

        max_inflow = max((p["total_net"] for p in flow_points), default=0)
        min_inflow = min((p["total_net"] for p in flow_points), default=0)

        sentiment = "neutral"
        if total_net > 200_000_000:
            sentiment = "very_bullish"
        elif total_net > 50_000_000:
            sentiment = "bullish"
        elif total_net < -200_000_000:
            sentiment = "very_bearish"
        elif total_net < -50_000_000:
            sentiment = "bearish"

        return {
            "sh_net_flow": round(sh_net / 1e8, 2),
            "sz_net_flow": round(sz_net / 1e8, 2),
            "total_net_flow": round(total_net / 1e8, 2),
            "total_net_flow_raw": total_net,
            "max_inflow": round(max_inflow / 1e8, 2),
            "min_inflow": round(min_inflow / 1e8, 2),
            "data_points": len(flow_points),
            "sentiment": sentiment,
            "unit": "亿元",
        }
