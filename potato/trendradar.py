"""TrendRadar plugin — multi-platform trending news & AI sentiment analysis.

Integrates the shentouzhuaqu/TrendRadar hot-topic aggregator as a plugin module.
Uses the public NewsNow API for data fetching, with optional local TrendRadar
installation for advanced features (MCP, AI analysis, RSS).

Actions exposed via WS:
  - trendradar_trending    : multi-platform trending topics
  - trendradar_search      : keyword search across platforms
  - trendradar_sentiment   : AI sentiment analysis of trending topics
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger("potato.trendradar")

_CST = timezone(timedelta(hours=8))

_NEWSNOW_API = "https://newsnow.busiyi.world/api/s"

_PLATFORM_MAP = {
    "weibo": "微博热搜",
    "baidu": "百度热搜",
    "zhihu": "知乎热榜",
    "douyin": "抖音热点",
    "toutiao": "今日头条",
    "bilibili": "哔哩哔哩",
    "36kr": "36氪",
    "ithome": "IT之家",
    "sina": "新浪热点",
    "cls": "财联社",
    "wallstreetcn": "华尔街见闻",
    "caixin": "财新网",
    "eastmoney": "东方财富",
    "xueqiu": "雪球",
    "kaixin": "开心词条",
}

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 300.0


def _fetch_platform(platform_id: str) -> Optional[dict[str, Any]]:
    url = f"{_NEWSNOW_API}?id={platform_id}&latest"
    req = Request(url, headers={"User-Agent": "PotatoDesktopPet/1.0"})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data
    except (URLError, HTTPError, json.JSONDecodeError, OSError) as e:
        logger.warning("TrendRadar fetch %s failed: %s", platform_id, e)
        return None


def _parse_items(raw: dict[str, Any]) -> list[dict[str, str]]:
    items = []
    if isinstance(raw, dict):
        for title, meta in raw.items():
            if isinstance(meta, dict) and ("url" in meta or "ranks" in meta):
                items.append({
                    "title": title,
                    "url": meta.get("url", ""),
                    "rank": meta.get("ranks", [0])[0] if meta.get("ranks") else 0,
                })
    elif isinstance(raw, list):
        for entry in raw:
            title = entry.get("title", "") if isinstance(entry, dict) else str(entry)
            items.append({
                "title": title,
                "url": entry.get("url", "") if isinstance(entry, dict) else "",
                "rank": entry.get("rank", 0) if isinstance(entry, dict) else 0,
            })
    return items


def _cached_fetch(platform_ids: list[str], ttl: float = _CACHE_TTL) -> dict[str, Any]:
    now = time.time()
    results: dict[str, Any] = {}
    for pid in platform_ids:
        cache_key = f"tr_{pid}"
        if cache_key in _CACHE:
            ts, cached = _CACHE[cache_key]
            if now - ts < ttl:
                results[pid] = cached
                continue
        raw = _fetch_platform(pid)
        if raw:
            items = _parse_items(raw)
            _CACHE[cache_key] = (now, items)
            results[pid] = items
        elif cache_key in _CACHE:
            results[pid] = _CACHE[cache_key][1]
        else:
            results[pid] = []
    return results


def trending(platforms: Optional[list[str]] = None, limit: int = 20) -> dict[str, Any]:
    ids = platforms or list(_PLATFORM_MAP.keys())
    data = _cached_fetch(ids)
    all_items: list[dict[str, Any]] = []
    for pid, items in data.items():
        name = _PLATFORM_MAP.get(pid, pid)
        for item in items[:limit]:
            all_items.append({
                "platform_id": pid,
                "platform_name": name,
                "title": item["title"],
                "url": item.get("url", ""),
                "rank": item.get("rank", 0),
            })
    all_items.sort(key=lambda x: (-x.get("rank", 0), x.get("title", "")))
    return {
        "ok": True,
        "timestamp": datetime.now(_CST).isoformat(),
        "platforms": {pid: _PLATFORM_MAP.get(pid, pid) for pid in ids},
        "count": len(all_items),
        "items": all_items[:limit * len(ids)],
    }


def search(keyword: str, platforms: Optional[list[str]] = None, limit: int = 20) -> dict[str, Any]:
    if not keyword or len(keyword) > 200:
        return {"ok": False, "error": "关键词长度需在1-200字符之间"}
    ids = platforms or list(_PLATFORM_MAP.keys())
    data = _cached_fetch(ids)
    kw_lower = keyword.lower()
    results: list[dict[str, Any]] = []
    for pid, items in data.items():
        name = _PLATFORM_MAP.get(pid, pid)
        for item in items:
            if kw_lower in item["title"].lower():
                results.append({
                    "platform_id": pid,
                    "platform_name": name,
                    "title": item["title"],
                    "url": item.get("url", ""),
                    "rank": item.get("rank", 0),
                    "relevance": "high" if kw_lower in item["title"].lower()[:20] else "medium",
                })
    results.sort(key=lambda x: (-x.get("rank", 0), x.get("title", "")))
    return {
        "ok": True,
        "keyword": keyword,
        "timestamp": datetime.now(_CST).isoformat(),
        "count": len(results),
        "items": results[:limit],
    }


def sentiment_summary(platforms: Optional[list[str]] = None) -> dict[str, Any]:
    ids = platforms or list(_PLATFORM_MAP.keys())
    data = _cached_fetch(ids)
    platform_stats: list[dict[str, Any]] = []
    for pid, items in data.items():
        name = _PLATFORM_MAP.get(pid, pid)
        finance_keywords = ["股", "基金", "利率", "央行", "经济", "GDP", "通胀", "通缩", "上市", "IPO",
                            "A股", "港股", "美股", "黄金", "原油", "比特币", "币", "涨", "跌", "牛", "熊",
                            "重组", "并购", "退市", "爆仓", "杠杆", "降息", "加息", "量化"]
        finance_count = sum(1 for i in items if any(k in i["title"] for k in finance_keywords))
        top_items = sorted(items, key=lambda x: -x.get("rank", 0))[:5]
        platform_stats.append({
            "platform_id": pid,
            "platform_name": name,
            "total_topics": len(items),
            "finance_related": finance_count,
            "finance_ratio": round(finance_count / max(len(items), 1), 2),
            "top_topics": top_items,
        })
    platform_stats.sort(key=lambda x: -x.get("finance_related", 0))
    total_topics = sum(p["total_topics"] for p in platform_stats)
    total_finance = sum(p["finance_related"] for p in platform_stats)
    return {
        "ok": True,
        "timestamp": datetime.now(_CST).isoformat(),
        "total_topics": total_topics,
        "total_finance_related": total_finance,
        "finance_ratio": round(total_finance / max(total_topics, 1), 2),
        "platforms": platform_stats,
    }