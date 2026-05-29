"""Iwencai natural language stock screening — 问财智能选股.

Two API endpoints:
1. /v1/query2data — Natural language market/stock queries (选股/宏观/指数/事件)
2. /v1/comprehensive/search — News/reports/investor/announcement search

Both require IWENCAI_API_KEY (Bearer token).
Falls back to free web scraping if no key configured.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

import httpx

logger = logging.getLogger("potato.iwencai")

_BASE_URL = "https://openapi.iwencai.com"
_WEB_URL = "https://www.iwencai.com/customized/chart/get-robot-data"

_HEADERS_BASE = {
    "Content-Type": "application/json",
    "X-Claw-Call-Type": "normal",
    "X-Claw-Plugin-Id": "none",
    "X-Claw-Plugin-Version": "none",
    "app_id": "AIME_SKILL",
}

_TIMEOUT = httpx.Timeout(connect=8.0, read=30.0, write=10.0, pool=30.0)


def _get_api_key() -> str:
    key = os.environ.get("IWENCAI_API_KEY", "")
    if not key:
        try:
            from potato.vault import Vault
            key = Vault().get("IWENCAI_API_KEY") or ""
        except Exception:
            pass
    return key.strip()


class IwencaiClient:
    """Iwencai API client for natural language stock queries."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or _get_api_key()

    def _headers(self, skill_id: str = "query2data") -> dict[str, str]:
        trace_id = uuid.uuid4().hex
        headers = dict(_HEADERS_BASE)
        headers["Authorization"] = f"Bearer {self.api_key}"
        headers["X-Claw-Skill-Id"] = skill_id
        headers["X-Claw-Skill-Version"] = "1.0.0"
        headers["X-Claw-Trace-Id"] = trace_id
        return headers

    def query(self, question: str, page: int = 1, limit: int = 10) -> dict[str, Any]:
        """Natural language query for stock/market data.

        Args:
            question: Natural language question (e.g. "连涨3天的股票", "贵州茅台最新价")
            page: Page number (1-based)
            limit: Results per page (max 100)

        Returns:
            dict with 'ok', 'data', 'total', 'question' keys
        """
        if not self.api_key:
            return _web_scrape_query(question, page, limit)

        headers = self._headers("query2data")
        payload = {
            "query": question,
            "page": str(page),
            "limit": str(limit),
            "is_cache": "1",
            "expand_index": "true",
            "app_id": "AIME_SKILL",
        }

        try:
            resp = httpx.post(
                f"{_BASE_URL}/v1/query2data",
                headers=headers,
                json=payload,
                timeout=_TIMEOUT,
            )
            data = resp.json()

            if resp.status_code != 200:
                logger.warning("Iwencai query failed: HTTP %d", resp.status_code)
                return {"ok": False, "error": f"HTTP {resp.status_code}", "question": question}

            if data.get("status_code") != 0:
                msg = data.get("status_msg", "unknown error")
                logger.warning("Iwencai query error: %s", msg)
                return {"ok": False, "error": msg, "question": question}

            datas = data.get("datas") or []
            return {
                "ok": True,
                "data": datas,
                "total": data.get("code_count", len(datas)),
                "question": question,
                "source": "iwencai_api",
            }

        except httpx.TimeoutException:
            logger.warning("Iwencai query timeout for: %s", question[:50])
            return {"ok": False, "error": "查询超时", "question": question}
        except Exception as e:
            logger.warning("Iwencai query error: %s", e)
            return {"ok": False, "error": str(e)[:200], "question": question}

    def search(
        self,
        keyword: str,
        channel: str = "news",
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search news, reports, investor info, or announcements.

        Args:
            keyword: Search keyword
            channel: One of 'news', 'report', 'investor', 'announcement'
            limit: Max results

        Returns:
            dict with 'ok', 'data', 'total', 'keyword', 'channel' keys
        """
        if not self.api_key:
            return {"ok": False, "error": "需要IWENCAI_API_KEY才能搜索资讯", "keyword": keyword}

        valid_channels = {"news", "report", "investor", "announcement"}
        if channel not in valid_channels:
            channel = "news"

        headers = self._headers("news-search")
        payload = {
            "channels": [channel],
            "app_id": "AIME_SKILL",
            "query": keyword,
        }

        try:
            resp = httpx.post(
                f"{_BASE_URL}/v1/comprehensive/search",
                headers=headers,
                json=payload,
                timeout=_TIMEOUT,
            )
            data = resp.json()

            if resp.status_code != 200:
                return {"ok": False, "error": f"HTTP {resp.status_code}", "keyword": keyword}

            items = data.get("data") or []
            results = []
            for item in items[:limit]:
                results.append({
                    "title": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "url": item.get("url", ""),
                    "publish_date": item.get("publish_date", ""),
                    "channel": channel,
                })

            return {
                "ok": True,
                "data": results,
                "total": len(results),
                "keyword": keyword,
                "channel": channel,
                "source": "iwencai_search",
            }

        except httpx.TimeoutException:
            return {"ok": False, "error": "搜索超时", "keyword": keyword}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200], "keyword": keyword}

    def select_stocks(self, query: str, limit: int = 20) -> dict[str, Any]:
        """Smart stock screening with natural language.

        Args:
            query: Natural language screening criteria (e.g. "连续涨停3天的股票")
            limit: Max stocks to return

        Returns:
            dict with 'ok', 'stocks', 'total', 'query' keys
        """
        result = self.query(query, page=1, limit=limit)
        if not result.get("ok"):
            return result

        datas = result.get("data", [])
        stocks = []
        for item in datas:
            stocks.append({
                "code": item.get("代码", item.get("code", "")),
                "name": item.get("名称", item.get("name", "")),
                "raw": item,
            })

        return {
            "ok": True,
            "stocks": stocks,
            "total": result.get("total", len(stocks)),
            "query": query,
            "source": "iwencai_select",
        }

    def select_sector(self, keyword: str) -> dict[str, Any]:
        """Sector/concept screening."""
        return self.query(f"属于{keyword}板块的股票")

    def query_macro(self, indicator: str) -> dict[str, Any]:
        """Macro economic data query (GDP, CPI, PMI, etc.)."""
        return self.query(f"{indicator}最新数据")

    def query_index(self, index_name: str) -> dict[str, Any]:
        """Index data query."""
        return self.query(f"{index_name}指数行情")


def _web_scrape_query(question: str, page: int = 1, limit: int = 10) -> dict[str, Any]:
    """Fallback: free web scraping query (no API key needed, limited reliability)."""
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    payload = {
        "source": "Ths_iwencai_Xuangu",
        "version": "2.0",
        "query_area": "",
        "block_list": "",
        "add_info": json.dumps({
            "urp": {"scene": 1, "company": 1, "business": 1},
            "contentType": "json",
            "searchInfo": True,
        }),
        "question": question,
        "perpage": str(limit),
        "page": page,
        "secondary_intent": "stock",
        "log_info": json.dumps({"input_type": "typewrite"}),
        "rsh": "",
    }

    try:
        resp = httpx.post(_WEB_URL, headers=headers, json=payload, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return {"ok": False, "error": f"HTTP {resp.status_code}", "question": question}

        data = resp.json()
        answer = data.get("data", {}).get("answer", [])
        if not answer:
            return {"ok": True, "data": [], "total": 0, "question": question, "source": "iwencai_web"}

        result_data = []
        for ans in answer:
            txt = ans.get("txt", {})
            if isinstance(txt, dict):
                content = txt.get("content", [])
                for item in content:
                    if isinstance(item, dict) and item.get("component"):
                        comp = item["component"]
                        if isinstance(comp, dict):
                            result_data.append(comp.get("data", comp))

        if not result_data and answer:
            result_data = [{"raw": answer}]

        return {
            "ok": True,
            "data": result_data[:limit],
            "total": len(result_data),
            "question": question,
            "source": "iwencai_web",
        }

    except httpx.TimeoutException:
        return {"ok": False, "error": "网页查询超时", "question": question}
    except Exception as e:
        logger.warning("Iwencai web scrape error: %s", e)
        return {"ok": False, "error": str(e)[:200], "question": question}


def format_iwencai_to_text(result: dict[str, Any]) -> str:
    """Format Iwencai query result to human-readable text."""
    if not result.get("ok"):
        return f"查询失败: {result.get('error', '未知错误')}"

    source = result.get("source", "")
    data = result.get("data", [])

    if source == "iwencai_search":
        items = result.get("data", [])
        if not items:
            return "未找到相关资讯"
        lines = [f"📊 {result.get('keyword', '')} - {result.get('channel', 'news')}搜索结果"]
        for i, item in enumerate(items[:10], 1):
            title = item.get("title", "无标题")
            date = item.get("publish_date", "")
            summary = item.get("summary", "")[:80]
            lines.append(f"{i}. {title} ({date})\n   {summary}")
        return "\n".join(lines)

    if source == "iwencai_select":
        stocks = result.get("stocks", [])
        if not stocks:
            return f"「{result.get('query', '')}」未筛选到符合条件的股票"
        lines = [f"筛选「{result.get('query', '')}」共{result.get('total', len(stocks))}只:"]
        for s in stocks[:15]:
            code = s.get("code", "")
            name = s.get("name", "")
            lines.append(f"  {name}({code})")
        if len(stocks) > 15:
            lines.append(f"  ...还有{len(stocks) - 15}只")
        return "\n".join(lines)

    if not data:
        return f"「{result.get('question', '')}」未查到数据"

    lines = [f"📊 {result.get('question', '')}"]
    for item in data[:10]:
        if isinstance(item, dict):
            name = item.get("名称", item.get("name", ""))
            code = item.get("代码", item.get("code", ""))
            if name or code:
                detail_parts = []
                for k, v in item.items():
                    if k not in ("名称", "name", "代码", "code", "raw") and v:
                        detail_parts.append(f"{k}:{v}")
                detail = " | ".join(detail_parts[:5])
                lines.append(f"  {name}({code}) {detail}")
    return "\n".join(lines)