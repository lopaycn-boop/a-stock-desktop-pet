"""EastMoney AI SaaS integration — 8 financial analysis APIs.

Provides structured financial data from EastMoney's AI SaaS platform:
- Entity recognition (stock code lookup)
- Earnings review (业绩点评)
- Financial QA (金融问答)
- Industry research (行业研究)
- Tracking report (跟踪报告)
- Comparable company analysis (可比公司分析)
- Hotspot discovery (热点发现)
- Financial data query (金融数据搜索)
- Financial news search (金融资讯搜索)

Plus real-time stock data:
- Anomaly monitoring (22 types of 异动)
- Dragon Tiger List (龙虎榜)
- Chip distribution (筹码分布)
- K-line data with indicators
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger("potato.eastmoney")

# ── API Endpoints ────────────────────────────────────────────────────────

EM_ENTITY_API = "https://ai-saas.eastmoney.com/proxy/entity/dialogTagsV2"
EM_REPORT_LIST_API = "https://ai-saas.eastmoney.com/proxy/app-robo-advisor-api/assistant/write/choice/reportList"
EM_PERFORMANCE_COMMENT_API = "https://ai-saas.eastmoney.com/proxy/app-robo-advisor-api/assistant/write/performance/comment"
EM_FINANCIAL_QA_API = "https://ai-saas.eastmoney.com/proxy/app-robo-advisor-api/assistant/ask"
EM_INDUSTRY_RESEARCH_API = "https://ai-saas.eastmoney.com/proxy/app-robo-advisor-api/assistant/write/industry/research"
EM_TRACKING_REPORT_API = "https://ai-saas.eastmoney.com/proxy/app-robo-advisor-api/assistant/write/tracking/report"
EM_SEARCH_DATA_API = "https://ai-saas.eastmoney.com/proxy/b/mcp/tool/searchData"
EM_SEARCH_NEWS_API = "https://ai-saas.eastmoney.com/proxy/b/mcp/tool/searchNews"
EM_COMPARABLE_COMPANY_API = "https://ai-saas.eastmoney.com/proxy/app-robo-advisor-api/assistant/comparable-company-analysis"
EM_HOTSPOT_DISCOVERY_API = "https://ai-saas.eastmoney.com/proxy/app-robo-advisor-api/assistant/hotspot-discovery"

EM_QUOTE_API = "https://push2.eastmoney.com/api/qt/clist/get"
EM_KLINE_API = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EM_CHANGES_API = "https://push2ex.eastmoney.com/get/qt=changes"
EM_HOT_TABLES_API = "https://push2ex.eastmoney.com/get/qt=hot_tables"
EM_CHIP_API = "https://push2his.eastmoney.com/api/qt/chipdistribution/get"

_TIMEOUT = httpx.Timeout(connect=8.0, read=15.0, write=10.0, pool=30.0)


# ── Financial Sentiment Analysis ──────────────────────────────────────────

POSITIVE_WORDS = {
    "涨": 1.0, "上涨": 2.0, "涨停": 3.0, "牛市": 3.0, "反弹": 2.0, "新高": 2.5,
    "利好": 2.5, "增持": 2.0, "买入": 2.0, "推荐": 1.5, "看多": 2.0,
    "盈利": 2.0, "增长": 2.0, "超预期": 2.5, "强劲": 1.5, "回升": 1.5,
    "复苏": 2.0, "突破": 2.0, "创新高": 3.0, "回暖": 1.5, "上扬": 1.5,
    "利好消息": 3.0, "收益增长": 2.5, "利润增长": 2.5, "业绩优异": 2.5,
    "潜力股": 2.0, "绩优股": 2.0, "强势": 1.5, "走高": 1.5, "攀升": 1.5,
    "大涨": 2.5, "飙升": 3.0, "井喷": 3.0, "暴涨": 3.0,
}

NEGATIVE_WORDS = {
    "跌": 2.0, "下跌": 2.0, "跌停": 3.0, "熊市": 3.0, "回调": 2.5, "新低": 2.5,
    "利空": 2.5, "减持": 2.0, "卖出": 2.0, "看空": 2.0, "亏损": 2.5,
    "下滑": 2.0, "萎缩": 2.0, "不及预期": 2.5, "疲软": 1.5, "恶化": 2.0,
    "衰退": 2.0, "跌破": 2.0, "创新低": 3.0, "走弱": 2.5, "下挫": 2.5,
    "利空消息": 3.0, "收益下降": 2.5, "利润下滑": 2.5, "业绩不佳": 2.5,
    "垃圾股": 2.0, "风险股": 2.0, "弱势": 2.5, "走低": 2.5, "缩量": 2.5,
    "大跌": 2.5, "暴跌": 3.0, "崩盘": 3.0, "跳水": 3.0, "重挫": 3.0,
    "跌超": 2.5, "跌逾": 2.5, "回吐": 3.0, "转跌": 3.0,
}

NEGATION_WORDS = {"不", "没", "无", "非", "未", "别", "勿"}
DEGREE_WORDS = {
    "非常": 1.8, "极其": 2.2, "太": 1.8, "很": 1.5,
    "比较": 0.8, "稍微": 0.6, "有点": 0.7, "显著": 1.5,
    "大幅": 1.8, "急剧": 2.0, "轻微": 0.6, "小幅": 0.7, "逾": 1.8, "超": 1.8,
}
TRANSITION_WORDS = {"但是", "然而", "不过", "却", "可是"}


def analyze_sentiment(text: str) -> dict[str, Any]:
    """Analyze financial sentiment of Chinese text.

    Returns dict with:
        - score: float (-3 to +3)
        - category: "看涨" / "看跌" / "中性"
        - positive_words: list of (word, weight) found
        - negative_words: list of (word, weight) found
    """
    if not text or not text.strip():
        return {"score": 0.0, "category": "中性", "positive_words": [], "negative_words": []}

    pos_found = []
    neg_found = []
    total_score = 0.0
    after_transition = False

    sentences = re.split(r"[。！？；\n]", text)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        for tw in TRANSITION_WORDS:
            if tw in sentence:
                after_transition = True
                break

        weight_multiplier = 1.5 if after_transition else 1.0

        for word, w in POSITIVE_WORDS.items():
            if word in sentence:
                has_negation = any(nw in sentence and sentence.index(nw) < sentence.index(word) for nw in NEGATION_WORDS if nw in sentence)
                if has_negation:
                    neg_found.append((word, w))
                    total_score -= w * weight_multiplier
                else:
                    for dw, df in DEGREE_WORDS.items():
                        if dw + word in sentence:
                            w *= df
                            break
                    pos_found.append((word, w))
                    total_score += w * weight_multiplier

        for word, w in NEGATIVE_WORDS.items():
            if word in sentence:
                has_negation = any(nw in sentence and sentence.index(nw) < sentence.index(word) for nw in NEGATION_WORDS if nw in sentence)
                if has_negation:
                    pos_found.append((word, w))
                    total_score += w * weight_multiplier
                else:
                    for dw, df in DEGREE_WORDS.items():
                        if dw + word in sentence:
                            w *= df
                            break
                    neg_found.append((word, w))
                    total_score -= w * weight_multiplier

    total_score = max(-3.0, min(3.0, total_score))
    if total_score > 0.5:
        category = "看涨"
    elif total_score < -0.5:
        category = "看跌"
    else:
        category = "中性"

    return {
        "score": round(total_score, 2),
        "category": category,
        "positive_words": pos_found[:10],
        "negative_words": neg_found[:10],
    }


# ── EastMoney AI SaaS Client ─────────────────────────────────────────────

class EastMoneyClient:
    """Client for EastMoney AI SaaS APIs."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._client = httpx.Client(timeout=_TIMEOUT, headers=self._base_headers())

    def _base_headers(self) -> dict[str, str]:
        em_base_info = json.dumps({"productType": "mx"}, ensure_ascii=False)
        headers = {
            "Content-Type": "application/json",
            "em_base_info": em_base_info,
        }
        if self.api_key:
            headers["em_api_key"] = self.api_key
        return headers

    def _post(self, url: str, payload: dict) -> dict[str, Any]:
        try:
            resp = self._client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("EastMoney API error: %s", _safe_err(exc))
            return {"ok": False, "error": str(exc)[:200]}

    def _get(self, url: str, params: dict | None = None) -> dict[str, Any]:
        try:
            resp = self._client.get(url, params=params or {})
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("EastMoney API error: %s", _safe_err(exc))
            return {"ok": False, "error": str(exc)[:200]}

    def entity_search(self, query: str) -> list[dict]:
        """Search for stock entities by name or code."""
        data = self._post(EM_ENTITY_API, {"query": query, "type": "1"})
        if not data.get("data", {}).get("entityList"):
            return []
        return data["data"]["entityList"][:10]

    def financial_qa(self, question: str, stock_code: str = "") -> str:
        """Ask a financial question, optionally about a specific stock."""
        payload: dict[str, Any] = {"question": question}
        if stock_code:
            payload["stockCode"] = stock_code
        data = self._post(EM_FINANCIAL_QA_API, payload)
        return data.get("data", {}).get("answer", "") or data.get("data", {}).get("content", "")

    def earnings_review(self, stock_code: str) -> str:
        """Get AI-generated earnings review for a stock."""
        data = self._post(EM_PERFORMANCE_COMMENT_API, {"stockCode": stock_code})
        return data.get("data", {}).get("content", "") or data.get("data", {}).get("answer", "")

    def industry_research(self, industry: str, stock_code: str = "") -> str:
        """Get AI-generated industry research report."""
        payload: dict[str, Any] = {"industry": industry}
        if stock_code:
            payload["stockCode"] = stock_code
        data = self._post(EM_INDUSTRY_RESEARCH_API, payload)
        return data.get("data", {}).get("content", "") or data.get("data", {}).get("answer", "")

    def tracking_report(self, stock_code: str) -> str:
        """Get AI-generated tracking report for a stock."""
        data = self._post(EM_TRACKING_REPORT_API, {"stockCode": stock_code})
        return data.get("data", {}).get("content", "") or data.get("data", {}).get("answer", "")

    def comparable_company(self, stock_code: str) -> str:
        """Get comparable company analysis."""
        data = self._post(EM_COMPARABLE_COMPANY_API, {"stockCode": stock_code})
        return data.get("data", {}).get("content", "") or data.get("data", {}).get("answer", "")

    def hotspot_discovery(self, keyword: str = "") -> str:
        """Discover market hotspots."""
        payload: dict[str, Any] = {}
        if keyword:
            payload["keyword"] = keyword
        data = self._post(EM_HOTSPOT_DISCOVERY_API, payload)
        return data.get("data", {}).get("content", "") or data.get("data", {}).get("answer", "")


# ── Real-time Market Data ────────────────────────────────────────────────

def get_stock_changes() -> list[dict]:
    """Get real-time stock data. Tries EastMoney, falls back to sorted Sina quotes."""
    result = _em_stock_changes()
    if result:
        return result
    return _sina_top_changes()


def _em_stock_changes() -> list[dict]:
    """EastMoney quote list API for top movers."""
    try:
        client = httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
        params = {
            "pn": "1",
            "pz": "20",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f2,f3,f4,f5,f6,f7,f12,f14,f15,f16,f17",
        }
        resp = client.get(EM_QUOTE_API, params=params)
        resp.raise_for_status()
        data = resp.json()
        diff = data.get("data", {}).get("diff", [])
        items = []
        for item in diff:
            items.append({
                "code": item.get("f12", ""),
                "name": item.get("f14", ""),
                "price": float(item.get("f2", 0) or 0),
                "change_pct": float(item.get("f3", 0) or 0),
                "volume": int(float(item.get("f6", 0) or 0)),
                "amplitude": float(item.get("f7", 0) or 0),
                "high": float(item.get("f15", 0) or 0),
                "low": float(item.get("f16", 0) or 0),
            })
        return items
    except Exception as exc:
        logger.debug("EM stock changes fallback: %s", _safe_err(exc))
        return []


def _sina_top_changes() -> list[dict]:
    """Sina batch quote as fallback for top movers."""
    codes = ["sh600519", "sz000001", "sz300750", "sh601318", "sz000858",
             "sh600036", "sz000651", "sh601012", "sz002714", "sh600276",
             "sz000333", "sh600887", "sz002415", "sh601166", "sz300059",
             "sh600030", "sz000002", "sh601688", "sz002304", "sh600309"]
    try:
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        client = httpx.Client(timeout=_TIMEOUT, headers=headers)
        resp = client.get(f"https://hq.sinajs.cn/list={','.join(codes)}")
        resp.raise_for_status()
        items = []
        for line in resp.text.strip().split("\n"):
            match = re.search(r'hq_str_([a-z]+\d+)="([^"]*)"', line)
            if not match:
                continue
            fields = match.group(2).split(",")
            if len(fields) < 32:
                continue
            code = match.group(1)[2:]
            name = fields[0]
            prev_close = float(fields[2]) if fields[2] else 0
            price = float(fields[3]) if fields[3] else 0
            change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0
            items.append({
                "code": code,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume": int(fields[8]) if fields[8] else 0,
                "high": float(fields[4]) if fields[4] else 0,
                "low": float(fields[5]) if fields[5] else 0,
            })
        items.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
        return items[:20]
    except Exception as exc:
        logger.debug("Sina top changes fallback: %s", _safe_err(exc))
        return []


EM_HOT_TABLES_DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def get_hot_tables(market: int = 1) -> list[dict]:
    """Get Dragon Tiger List (龙虎榜) data. Tries push2ex, then datacenter.

    Args:
        market: 1=A-stock, 2=HK, 3=US
    """
    result = _em_hot_tables_push2ex(market)
    if result:
        return result
    return _em_hot_tables_dc(market)


def _em_hot_tables_push2ex(market: int) -> list[dict]:
    """Original push2ex endpoint for Dragon Tiger List."""
    try:
        client = httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
        params = {
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15,f16,f17,f18",
            "fields2": "f51,f52,f53,f54,f55",
        }
        resp = client.get("https://push2ex.eastmoney.com/get/qt=hot_tables", params=params)
        if resp.status_code == 200:
            data = resp.json()
            diff = data.get("data", {}).get("diff", [])
            if diff:
                return diff
        return []
    except Exception:
        return []


def _em_hot_tables_dc(market: int) -> list[dict]:
    """EastMoney datacenter API for Dragon Tiger List."""
    market_map = {1: "沪A", 2: "港股", 3: "美股"}
    try:
        client = httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
        params = {
            "reportName": "RPT_DAILYBOARD_DETAILS",
            "columns": "ALL",
            "pageNumber": "1",
            "pageSize": "20",
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        }
        if market == 1:
            params["filter"] = '(MARKET="沪A")(MARKET="深A")(MARKET="创业板")'
        elif market == 2:
            params["filter"] = '(MARKET="港股")'
        resp = client.get(EM_HOT_TABLES_DC, params=params)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {})
        if result and result.get("data"):
            items = []
            for row in result["data"][:20]:
                items.append({
                    "code": row.get("SECURITY_CODE", ""),
                    "name": row.get("SECURITY_NAME_ABBR", ""),
                    "close_price": row.get("CLOSE_PRICE", 0),
                    "change_pct": row.get("CHANGE_RATE", 0),
                    "net_buy": row.get("NET_BUY_AMT", 0),
                    "buy_reason": row.get("EXPLAIN", ""),
                    "date": row.get("TRADE_DATE", ""),
                })
            return items
        return []
    except Exception as exc:
        logger.debug("Hot tables DC fallback: %s", _safe_err(exc))
        return []


def get_kline_data(stock_code: str, period: str = "101", start: str = "20250101", end: str = "20251231") -> list[str]:
    """Get K-line (candlestick) data. Tries EastMoney first, falls back to Tencent.

    Args:
        stock_code: 6-digit stock code
        period: klt=101 for daily, 102 for weekly, 103 for monthly
        start: start date YYYYMMDD
        end: end date YYYYMMDD
    """
    result = _em_kline(stock_code, period, start, end)
    if result:
        return result
    return _tencent_kline(stock_code, period)


def _em_kline(stock_code: str, period: str, start: str, end: str) -> list[str]:
    """EastMoney K-line API."""
    secid = f"1.{stock_code}" if stock_code.startswith(("6", "9")) else f"0.{stock_code}"
    try:
        client = httpx.Client(timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=30.0), follow_redirects=True)
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": period,
            "fqt": "1",
            "beg": start,
            "end": end,
            "ut": "fa5fd1943c7b386f172d6893dbbd0320",
        }
        resp = client.get(EM_KLINE_API, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("klines", [])
    except Exception as exc:
        logger.debug("EM K-line fallback: %s", _safe_err(exc))
        return []


def _tencent_kline(stock_code: str, period: str) -> list[str]:
    """Tencent Finance K-line API as fallback."""
    period_map = {"101": "day", "102": "week", "103": "month"}
    klt = period_map.get(period, "day")
    prefix = "sh" if stock_code.startswith(("6", "9")) else "sz"
    tencent_code = f"{prefix}{stock_code}"
    try:
        client = httpx.Client(timeout=httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=20.0))
        params = {"param": f"{tencent_code},{klt},,,300,qfq"}
        resp = client.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", params=params)
        resp.raise_for_status()
        data = resp.json()
        stock_data = data.get("data", {}).get(tencent_code, {})
        klines_raw = stock_data.get(klt, stock_data.get("qfq" + klt, []))
        if not klines_raw:
            return []
        result = []
        for row in klines_raw:
            if isinstance(row, list) and len(row) >= 6:
                date_str = str(row[0])
                open_p = row[1]
                close_p = row[2]
                high_p = row[3]
                low_p = row[4]
                vol = row[5]
                result.append(f"{date_str},{open_p},{close_p},{high_p},{low_p},{vol}")
        return result
    except Exception as exc:
        logger.warning("Tencent K-line error for %s: %s", stock_code, _safe_err(exc))
        return []


def get_chip_distribution(stock_code: str) -> dict[str, Any]:
    """Get chip/cost distribution (筹码分布) for a stock.

    Tries EastMoney first, falls back to Tencent cost distribution estimate.
    """
    result = _em_chip_distribution(stock_code)
    if result:
        return result
    return _tencent_chip_estimate(stock_code)


def _em_chip_distribution(stock_code: str) -> dict[str, Any]:
    """EastMoney chip distribution API."""
    secid = f"1.{stock_code}" if stock_code.startswith(("6", "9")) else f"0.{stock_code}"
    try:
        client = httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6,f7",
            "fields2": "f51,f52,f53,f54,f55",
        }
        resp = client.get(EM_CHIP_API, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {})
    except Exception as exc:
        logger.debug("EM chip distribution fallback: %s", _safe_err(exc))
        return {}


def _tencent_chip_estimate(stock_code: str) -> dict[str, Any]:
    """Estimate chip distribution from Tencent K-line data based on recent price range."""
    prefix = "sh" if stock_code.startswith(("6", "9")) else "sz"
    tencent_code = f"{prefix}{stock_code}"
    try:
        client = httpx.Client(timeout=httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=20.0))
        params = {"param": f"{tencent_code},day,,,60,qfq"}
        resp = client.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", params=params)
        resp.raise_for_status()
        data = resp.json()
        stock_data = data.get("data", {}).get(tencent_code, {})
        klines = stock_data.get("day", stock_data.get("qfqday", []))
        if not klines or len(klines) < 5:
            return {"source": "tencent_estimate", "code": stock_code, "prices": [], "volumes": []}
        prices = []
        volumes = []
        for row in klines[-60:]:
            if isinstance(row, list) and len(row) >= 6:
                prices.append(float(row[2]))
                volumes.append(float(row[5]))
        if not prices:
            return {"source": "tencent_estimate", "code": stock_code, "prices": [], "volumes": []}
        price_min = min(prices)
        price_max = max(prices)
        price_avg = sum(prices) / len(prices)
        vol_avg = sum(volumes) / len(volumes) if volumes else 0
        return {
            "source": "tencent_estimate",
            "code": stock_code,
            "price_range": [round(price_min, 2), round(price_max, 2)],
            "price_avg": round(price_avg, 2),
            "vol_avg": round(vol_avg, 0),
            "data_len": len(klines),
        }
    except Exception as exc:
        logger.debug("Tencent chip estimate fallback: %s", _safe_err(exc))
        return {}


def get_realtime_quote(stock_code: str) -> dict[str, Any]:
    """Get real-time stock quote. Tries Sina first, falls back to EastMoney."""
    result = _sina_quote(stock_code)
    if result:
        return result
    return _em_quote(stock_code)


def _sina_quote(stock_code: str) -> dict[str, Any]:
    """Fetch quote from Sina Finance (requires Referer header)."""
    prefix = "sh" if stock_code.startswith(("6", "9")) else "sz"
    sina_code = f"{prefix}{stock_code}"
    try:
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        }
        client = httpx.Client(timeout=_TIMEOUT, headers=headers)
        resp = client.get(f"https://hq.sinajs.cn/list={sina_code}")
        resp.raise_for_status()
        raw = resp.text
        match = re.search(r'="([^"]*)"', raw)
        if not match:
            return {}
        fields = match.group(1).split(",")
        if len(fields) < 32:
            return {}
        return {
            "code": stock_code,
            "name": fields[0],
            "open": float(fields[1]) if fields[1] else 0,
            "prev_close": float(fields[2]) if fields[2] else 0,
            "price": float(fields[3]) if fields[3] else 0,
            "high": float(fields[4]) if fields[4] else 0,
            "low": float(fields[5]) if fields[5] else 0,
            "volume": int(fields[8]) if fields[8] else 0,
            "amount": float(fields[9]) if fields[9] else 0,
            "change_pct": round((float(fields[3]) - float(fields[2])) / float(fields[2]) * 100, 2) if fields[2] and float(fields[2]) > 0 else 0,
        }
    except Exception as exc:
        logger.debug("Sina quote fallback for %s: %s", stock_code, _safe_err(exc))
        return {}


def _em_quote(stock_code: str) -> dict[str, Any]:
    """Fetch quote from EastMoney push2 API as fallback."""
    secid = f"1.{stock_code}" if stock_code.startswith(("6", "9")) else f"0.{stock_code}"
    try:
        client = httpx.Client(timeout=_TIMEOUT)
        params = {
            "secid": secid,
            "fields": "f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f107,f170",
            "ut": "fa5fd1943c7b386f172d6893dbbd0320",
        }
        resp = client.get(EM_QUOTE_API, params=params)
        resp.raise_for_status()
        data = resp.json()
        d = data.get("data", {})
        if not d:
            return {}
        prev_close = float(d.get("f60", 0) or 0)
        price = float(d.get("f43", 0) or 0)
        change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0
        return {
            "code": d.get("f57", stock_code),
            "name": d.get("f58", ""),
            "open": float(d.get("f46", 0) or 0),
            "prev_close": prev_close,
            "price": price,
            "high": float(d.get("f44", 0) or 0),
            "low": float(d.get("f45", 0) or 0),
            "volume": int(d.get("f47", 0) or 0),
            "amount": float(d.get("f48", 0) or 0),
            "change_pct": change_pct,
        }
    except Exception as exc:
        logger.warning("EM quote fallback error for %s: %s", stock_code, _safe_err(exc))
        return {}


def _safe_err(exc: Exception) -> str:
    msg = str(exc)
    return msg[:120] if len(msg) > 120 else msg