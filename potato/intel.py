from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import httpx

from potato.config import load_settings
from potato.llm import chat

logger = logging.getLogger("potato.intel")

RSS_QUERIES = (
    "A股 市场 行情",
    "沪深 板块 资金流向",
    "北向资金 沪深港通",
    "A股 政策 监管",
)


def fetch_headlines(*, limit_per_feed: int = 4) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    with httpx.Client(timeout=25.0, follow_redirects=True) as client:
        for query in RSS_QUERIES:
            url = (
                "https://news.google.com/rss/search?q="
                + quote_plus(query)
                + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
            )
            try:
                resp = client.get(url, headers={"User-Agent": "xiaotudou-astock/1.0"})
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
                for item in root.findall(".//item")[:limit_per_feed]:
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    if not title or title in seen:
                        continue
                    seen.add(title)
                    items.append({"title": title, "link": link, "query": query})
            except Exception as exc:
                logger.warning("RSS fetch failed (%s): %s", query, exc)
    return items[:12]


def run_daily_intel(*, push: bool = True) -> dict[str, Any]:
    settings = load_settings()
    run_id = f"intel-{uuid.uuid4().hex[:10]}"

    result: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "headlines": [],
        "analysis": "",
        "llm_ok": False,
    }

    try:
        headlines = fetch_headlines()
        result["headlines"] = headlines

        news_block = "\n".join(f"- {h['title']}" for h in headlines[:8]) or "- （暂无抓取到资讯标题）"

        prompt = f"""请基于以下 A 股相关资讯，输出「每日 A 股操盘简报」（中文，300-500字）：

## 最新资讯标题（Google News RSS）
{news_block}

要求：
1. 总结今日最值得关注的 2-3 个 A 股主题（板块/政策/资金流向）
2. 结合沪深两市行情特征给出分析
3. 给出保守操作建议（可 HOLD）
4. 不要编造未提供的事实
"""

        llm = chat(
            prompt,
            system="你是小土豆的A股资讯分析模块，保守、纪律优先，输出结构化中文简报。",
            settings=settings,
        )
        if llm.get("ok"):
            result["analysis"] = llm["content"]
            result["llm_ok"] = True
        else:
            lines = ["【规则摘要 — 未配置 DEEPSEEK_API_KEY】", "", "资讯标题:"]
            for h in headlines[:5]:
                lines.append(f"- {h['title'][:100]}")
            result["analysis"] = "\n".join(lines)
            result["llm_error"] = llm.get("error")

        result["status"] = "completed"
        result["finished_at"] = datetime.now(timezone.utc).isoformat()

        if push:
            from potato.notifications import BotNotifier, format_intel_message

            notify = BotNotifier(settings).notify(format_intel_message(result))
            result["notify"] = notify

        return result
    except Exception as exc:
        logger.exception("Daily intel failed")
        result["status"] = "failed"
        result["error"] = str(exc)
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        return result
