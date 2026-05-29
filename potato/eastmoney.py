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
    """Get real-time stock anomalies (异动) from EastMoney.

    Returns list of anomaly dicts with stock code, name, type, price, change%.
    22 anomaly types: 火箭发射, 快速反弹, 大笔买入, 封涨停板, etc.
    """
    try:
        client = httpx.Client(timeout=_TIMEOUT)
        resp = client.get("https://push2ex.eastmoney.com/get/qt=changes")
        resp.raise_for_status()
        data = resp.json()
        items = []
        for item in data.get("data", {}).get("diff", []):
            items.append({
                "code": item.get("c", ""),
                "name": item.get("n", ""),
                "price": float(item.get("p", 0)),
                "change_pct": float(item.get("zdp", 0)),
                "volume": int(item.get("v", 0)),
            })
        return items
    except Exception as exc:
        logger.warning("Stock changes API error: %s", _safe_err(exc))
        return []


def get_hot_tables(market: int = 1) -> list[dict]:
    """Get Dragon Tiger List (龙虎榜) data.

    Args:
        market: 1=A-stock, 2=HK, 3=US
    """
    try:
        client = httpx.Client(timeout=_TIMEOUT)
        params = {
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15,f16,f17,f18",
            "fields2": "f51,f52,f53,f54,f55",
            "market": market,
        }
        resp = client.get("https://push2ex.eastmoney.com/get/qt=hot_tables", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("diff", [])
    except Exception as exc:
        logger.warning("Hot tables API error: %s", _safe_err(exc))
        return []


def get_chip_distribution(stock_code: str) -> dict[str, Any]:
    """Get chip/cost distribution (筹码分布) for a stock.

    Shows how shares are distributed across price levels.
    """
    try:
        client = httpx.Client(timeout=_TIMEOUT)
        params = {
            "secid": f"1.{stock_code}" if stock_code.startswith("6") else f"0.{stock_code}",
            "fields1": "f1,f2,f3,f4,f5,f6,f7",
            "fields2": "f51,f52,f53,f54,f55",
        }
        resp = client.get(EM_CHIP_API, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {})
    except Exception as exc:
        logger.warning("Chip distribution API error: %s", _safe_err(exc))
        return {}


def get_realtime_quote(stock_code: str) -> dict[str, Any]:
    """Get real-time stock quote from Sina Finance.

    Args:
        stock_code: 6-digit stock code (e.g. "600519" for 贵州茅台)
    """
    prefix = "sh" if stock_code.startswith(("6", "9")) else "sz"
    sina_code = f"{prefix}{stock_code}"
    try:
        client = httpx.Client(timeout=_TIMEOUT)
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
        logger.warning("Quote API error for %s: %s", stock_code, _safe_err(exc))
        return {}


def _safe_err(exc: Exception) -> str:
    msg = str(exc)
    return msg[:120] if len(msg) > 120 else msg