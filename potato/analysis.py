"""AI-driven stock analysis — DeepSeek analyzes news, selects stocks, explains reasoning.

Flow:
1. Fetch personalized news based on user preferences (sectors, stocks, interests)
2. Scrape real-time data from user's trading platforms via browser
3. DeepSeek deep analysis: market trends + news correlation + risk assessment
4. Stock selection with detailed reasoning (why this stock?)
5. Generate buy/sell recommendations with confidence scores
6. Push daily briefing to user via desktop pet
"""

from __future__ import annotations

import json
import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import asyncio
import httpx

from potato.config import load_settings
from potato.llm import chat

logger = logging.getLogger("potato.analysis")


def fetch_stock_news(
    queries: list[str],
    *,
    limit_per_feed: int = 5,
) -> list[dict[str, str]]:
    """Fetch news from Google News RSS for given stock/sector queries."""
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    with httpx.Client(timeout=25.0, follow_redirects=True) as client:
        for query in queries:
            url = (
                "https://news.google.com/rss/search?q="
                + quote_plus(query)
                + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
            )
            try:
                resp = client.get(url, headers={"User-Agent": "potato-trader/1.0"})
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
                for item in root.findall(".//item")[:limit_per_feed]:
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    pub_date = (item.findtext("pubDate") or "").strip()
                    if not title or title in seen:
                        continue
                    seen.add(title)
                    items.append({
                        "title": title,
                        "link": link,
                        "pub_date": pub_date,
                        "query": query,
                    })
            except Exception as exc:
                logger.warning("RSS fetch failed (%s): %s", query, exc)
    return items[:30]


def build_news_queries(user_prefs: dict[str, Any]) -> list[str]:
    """Build search queries from user preferences."""
    queries = []
    for sector in user_prefs.get("sectors", []):
        queries.append(f"{sector} 股票 行情")
    for stock in user_prefs.get("watchlist", []):
        queries.append(f"{stock} 最新消息")
    queries.extend(user_prefs.get("custom_queries", []))
    if not queries:
        queries = ["股票市场 今日行情", "美股 热门", "A股 涨停", "加密货币 行情"]
    return queries


async def analyze_stocks(
    news: list[dict[str, str]],
    portfolio_text: str = "",
    user_prefs: dict[str, Any] | None = None,
    platform_names: str = "",
) -> dict[str, Any]:
    """DeepSeek deep analysis: news → stock selection → reasoning.

    Returns structured JSON with:
    - market_summary: 市场整体分析
    - stock_picks: 选股推荐 + 每只股票的详细理由
    - risk_warnings: 风险提示
    - action_plan: 今日操作计划 (buy/sell/hold)
    """
    settings = load_settings()
    run_id = f"analysis-{uuid.uuid4().hex[:8]}"
    prefs = user_prefs or {}

    news_block = "\n".join(
        f"- [{n.get('pub_date', '')}] {n['title']} (来源: {n.get('query', '')})"
        for n in news[:20]
    ) or "（暂无抓取到新闻）"

    portfolio_block = portfolio_text[:2000] if portfolio_text else "（未获取到持仓信息）"
    sectors = ", ".join(prefs.get("sectors", [])) or "未设置"
    watchlist = ", ".join(prefs.get("watchlist", [])) or "未设置"
    risk_level = prefs.get("risk_level", "conservative")

    prompt = f"""你是「小土豆」AI 操盘手的分析模块。请基于以下信息进行深度股票分析。

## 用户偏好
- 关注板块: {sectors}
- 自选股: {watchlist}
- 风险偏好: {risk_level}
- 使用的交易平台: {platform_names}

## 最新资讯
{news_block}

## 当前持仓（从交易平台页面提取）
{portfolio_block}

## 分析要求

请输出 JSON 格式（严格 JSON）：
{{
    "market_summary": "200字以内的市场整体分析",
    "stock_picks": [
        {{
            "symbol": "股票代码",
            "name": "股票名称",
            "action": "BUY/SELL/HOLD/WATCH",
            "confidence": 0.0-1.0,
            "reasoning": "为什么选这只股？详细分析（至少100字）",
            "entry_price": "建议买入价位",
            "target_price": "目标价位",
            "stop_loss": "止损价位",
            "news_correlation": "与哪条新闻相关"
        }}
    ],
    "risk_warnings": ["风险提示1", "风险提示2"],
    "action_plan": "今日操作建议（简洁版）",
    "sectors_outlook": {{
        "板块名": "看涨/看跌/震荡 + 简要理由"
    }}
}}

规则：
1. stock_picks 最多推荐 5 只股票
2. 必须给出清晰的选股理由，不能泛泛而谈
3. confidence 低于 0.6 的不应该推荐 BUY
4. 每只股票必须设止损
5. 根据用户风险偏好调整激进程度
6. 不要编造未在新闻中出现的事实"""

    result = await asyncio.to_thread(
        chat, prompt,
        system="你是专业的量化分析师「小土豆」，保守纪律优先，用中文输出结构化分析报告。",
        settings=settings,
        max_tokens=3000,
        task="analysis",
    )

    if result.get("ok"):
        try:
            analysis = json.loads(result["content"])
            return {
                "ok": True,
                "run_id": run_id,
                "analysis": analysis,
                "news_count": len(news),
                "model": result.get("model"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except json.JSONDecodeError:
            return {
                "ok": True,
                "run_id": run_id,
                "analysis_text": result["content"],
                "news_count": len(news),
                "note": "LLM returned non-JSON, raw text preserved",
            }
    else:
        return {
            "ok": False,
            "run_id": run_id,
            "error": result.get("error"),
            "fallback": _fallback_analysis(news),
        }


def _fallback_analysis(news: list[dict[str, str]]) -> dict[str, Any]:
    """Rule-based fallback when DeepSeek is unavailable."""
    return {
        "market_summary": "DeepSeek API 未配置，以下为规则摘要",
        "stock_picks": [],
        "risk_warnings": ["AI 分析不可用，请自行判断"],
        "action_plan": "HOLD — 等待 AI 分析恢复",
        "news_headlines": [n["title"] for n in news[:5]],
    }


def format_analysis_for_pet(analysis_result: dict[str, Any]) -> str:
    """Format analysis result as a chat message for the desktop pet."""
    if not analysis_result.get("ok"):
        return f"分析失败: {analysis_result.get('error', '未知错误')}"

    a = analysis_result.get("analysis") or analysis_result.get("fallback", {})
    lines = ["📊 小土豆今日股票分析", ""]

    if a.get("market_summary"):
        lines.append(f"【大盘】{a['market_summary']}")
        lines.append("")

    picks = a.get("stock_picks", [])
    if picks:
        lines.append("【选股推荐】")
        for i, p in enumerate(picks, 1):
            action_emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡", "WATCH": "👀"}.get(p.get("action", ""), "")
            lines.append(
                f"{i}. {action_emoji} {p.get('name', '')} ({p.get('symbol', '')}) — {p.get('action', 'HOLD')}"
            )
            lines.append(f"   理由: {p.get('reasoning', '')[:150]}")
            if p.get("entry_price"):
                lines.append(f"   建议价: {p['entry_price']} | 目标: {p.get('target_price', '-')} | 止损: {p.get('stop_loss', '-')}")
        lines.append("")

    if a.get("action_plan"):
        lines.append(f"【今日计划】{a['action_plan']}")

    warnings = a.get("risk_warnings", [])
    if warnings:
        lines.append("")
        lines.append("⚠️ " + " | ".join(warnings[:3]))

    return "\n".join(lines)
