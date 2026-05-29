"""Deep stock analysis engine — 小土豆选股分析核心.

Autonomous workflow:
    1. Scrape real-time data from trading platforms (via browser or API)
    2. Fetch news + macro context
    3. Technical indicators (MA/MACD/RSI/KDJ/Bollinger)
    4. AI deep analysis with structured reasoning
    5. Generate buy/sell/hold decisions with full explanation
    6. Risk validation before execution

Every decision MUST include:
    - WHY: 3-sentence minimum explanation
    - EVIDENCE: technical indicators + news correlation + sector trend
    - EXIT: entry price, target price, stop-loss price
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from potato.config import load_settings
from potato.llm import chat, research, analyze
from potato.eastmoney import (
    EastMoneyClient,
    analyze_sentiment,
    get_stock_changes,
    get_hot_tables,
    get_realtime_quote as em_get_realtime_quote,
)

logger = logging.getLogger("potato.trading.analyzer")


def _sma(prices: list[float], period: int) -> list[float | None]:
    result = []
    for i in range(len(prices)):
        if i < period - 1:
            result.append(None)
        else:
            window = prices[i - period + 1 : i + 1]
            result.append(sum(window) / period)
    return result


def _ema(prices: list[float], period: int) -> list[float | None]:
    if not prices:
        return []
    k = 2 / (period + 1)
    result = [prices[0]]
    for i in range(1, len(prices)):
        result.append(prices[i] * k + result[-1] * (1 - k))
    return result


def compute_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9,
) -> dict[str, float | None]:
    if len(closes) < slow + signal:
        return {"macd": None, "signal": None, "histogram": None}
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    valid_macd = [v for v in macd_line if v is not None]
    if len(valid_macd) < signal:
        return {"macd": None, "signal": None, "histogram": None}
    signal_line = _ema(valid_macd, signal)
    m = valid_macd[-1] if valid_macd else None
    s = signal_line[-1] if signal_line else None
    h = (m - s) if m is not None and s is not None else None
    return {"macd": m, "signal": s, "histogram": h}


def compute_kdj(
    highs: list[float], lows: list[float], closes: list[float], period: int = 9,
) -> dict[str, float | None]:
    n = len(closes)
    if n < period:
        return {"k": None, "d": None, "j": None}
    k_values, d_values = [50.0], [50.0]
    for i in range(1, n):
        start = max(0, i - period + 1)
        hn = max(highs[start : i + 1])
        ln = min(lows[start : i + 1])
        rsv = (closes[i] - ln) / (hn - ln) * 100 if hn != ln else 50.0
        k = 2 / 3 * k_values[-1] + 1 / 3 * rsv
        d = 2 / 3 * d_values[-1] + 1 / 3 * k
        k_values.append(k)
        d_values.append(d)
    j = 3 * k_values[-1] - 2 * d_values[-1]
    return {"k": round(k_values[-1], 2), "d": round(d_values[-1], 2), "j": round(j, 2)}


def compute_bollinger(
    closes: list[float], period: int = 20, num_std: float = 2.0,
) -> dict[str, float | None]:
    if len(closes) < period:
        return {"upper": None, "mid": None, "lower": None, "width": None}
    sma = _sma(closes, period)
    recent = closes[-period:]
    std = (sum((x - sma[-1]) ** 2 for x in recent) / period) ** 0.5
    mid = sma[-1]
    return {
        "upper": round(mid + num_std * std, 2),
        "mid": round(mid, 2),
        "lower": round(mid - num_std * std, 2),
        "width": round(num_std * std, 2),
    }


def compute_volume_ratio(volumes: list[int | float]) -> float | None:
    if len(volumes) < 6:
        return None
    avg5 = sum(volumes[-6:-1]) / 5
    today = volumes[-1]
    return round(today / avg5, 2) if avg5 > 0 else None


def technical_summary(
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if len(closes) < 2:
        return result
    result["price"] = closes[-1]
    result["change_pct"] = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2) if closes[-2] else 0
    ma5 = _sma(closes, 5)
    ma10 = _sma(closes, 10)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)
    for name, val in [("ma5", ma5), ("ma10", ma10), ("ma20", ma20), ("ma60", ma60)]:
        v = val[-1] if val and val[-1] is not None else None
        result[name] = round(v, 2) if v else None
    trend_up = None
    if ma5 and ma5[-1] and ma10 and ma10[-1] and ma20 and ma20[-1]:
        trend_up = ma5[-1] > ma10[-1] > ma20[-1]
    result["trend"] = "up" if trend_up else ("down" if trend_up is False else "flat")
    result["rsi"] = compute_rsi(closes)
    result["macd"] = compute_macd(closes)
    if highs and lows:
        result["kdj"] = compute_kdj(highs, lows, closes)
    result["bollinger"] = compute_bollinger(closes)
    if volumes:
        result["volume_ratio"] = compute_volume_ratio(volumes)
    current = closes[-1]
    b = result.get("bollinger", {})
    if b.get("mid"):
        if current > b["upper"]:
            result["boll_position"] = "above_upper"
        elif current < b["lower"]:
            result["boll_position"] = "below_lower"
        elif current > b["mid"]:
            result["boll_position"] = "upper_half"
        else:
            result["boll_position"] = "lower_half"
    return result


async def fetch_realtime_quote(symbol: str, platform: str = "eastmoney") -> dict[str, Any] | None:
    if symbol.startswith("6") or symbol.startswith("9"):
        market = "1"
    elif symbol.startswith("0") or symbol.startswith("3") or symbol.startswith("2"):
        market = "0"
    elif symbol.startswith("4") or symbol.startswith("8"):
        market = "0"
    else:
        market = "1"
    url = f"https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "secid": f"{market}.{symbol}",
        "fields": "f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f116,f117,f162,f170",
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                if data:
                    return {
                        "symbol": symbol,
                        "name": data.get("f58", ""),
                        "price": data.get("f43", 0) / 100 if data.get("f43") else None,
                        "open": data.get("f46", 0) / 100 if data.get("f46") else None,
                        "high": data.get("f44", 0) / 100 if data.get("f44") else None,
                        "low": data.get("f45", 0) / 100 if data.get("f45") else None,
                        "volume": data.get("f47", 0),
                        "amount": data.get("f48", 0),
                        "change_pct": data.get("f170", 0) / 100 if data.get("f170") else None,
                        "pe": data.get("f162", 0) / 100 if data.get("f162") else None,
                        "pb": data.get("f116", 0) / 100 if data.get("f116") else None,
                    }
    except Exception as e:
        logger.warning("Quote fetch failed for %s: %s", symbol, e)
    return None


async def fetch_kline(
    symbol: str, period: str = "k", count: int = 60, platform: str = "eastmoney",
) -> list[dict[str, Any]]:
    klt_map = {"k": "101", "d": "102", "w": "103", "m": "104"}
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": f"1.{symbol}" if symbol.startswith("6") else f"0.{symbol}",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "klt": klt_map.get(period, "101"),
        "fqt": "1",
        "end": "20500101",
        "lmt": str(count),
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                klines = data.get("klines", [])
                result = []
                for line in klines:
                    parts = line.split(",")
                    if len(parts) >= 7:
                        result.append({
                            "date": parts[0],
                            "open": float(parts[1]),
                            "close": float(parts[2]),
                            "high": float(parts[3]),
                            "low": float(parts[4]),
                            "volume": float(parts[5]),
                            "amount": float(parts[6]),
                        })
                return result
    except Exception as e:
        logger.warning("Kline fetch failed for %s: %s", symbol, e)
    return []


def _build_technical_context(klines: list[dict], quote: dict | None) -> str:
    closes = [k["close"] for k in klines[-60:]] if len(klines) >= 5 else []
    highs = [k["high"] for k in klines[-60:]] if klines else []
    lows = [k["low"] for k in klines[-60:]] if klines else []
    volumes = [k["volume"] for k in klines[-60:]] if klines else []

    if not closes:
        return "（技术指标数据不足）"

    tech = technical_summary(closes, highs, lows, volumes)
    lines = [f"当前价: {tech.get('price')}", f"涨跌幅: {tech.get('change_pct')}%"]

    if tech.get("trend"):
        trend_map = {"up": "多头排列↑", "down": "空头排列↓", "flat": "横盘震荡→"}
        lines.append(f"趋势: {trend_map.get(tech['trend'], tech['trend'])}")
    if tech.get("rsi") is not None:
        rsi_val = tech["rsi"]
        rsi_status = "超买" if rsi_val > 70 else ("超卖" if rsi_val < 30 else "中性")
        lines.append(f"RSI(14): {rsi_val:.1f} ({rsi_status})")
    macd = tech.get("macd", {})
    if macd.get("macd") is not None:
        lines.append(f"MACD: {macd['macd']:.4f}, 信号线: {macd['signal']:.4f}")
        if macd.get("histogram") is not None:
            hp = "金叉↑" if macd["histogram"] > 0 else "死叉↓"
            lines.append(f"MACD柱: {macd['histogram']:.4f} ({hp})")
    kdj = tech.get("kdj", {})
    if kdj.get("k") is not None:
        lines.append(f"KDJ: K={kdj['k']}, D={kdj['d']}, J={kdj['j']}")
    boll = tech.get("bollinger", {})
    if boll.get("mid") is not None:
        lines.append(f"布林带: 上={boll['upper']}, 中={boll['mid']}, 下={boll['lower']}")
    if tech.get("volume_ratio") is not None:
        vr = tech["volume_ratio"]
        lines.append(f"量比: {vr} ({'放量' if vr > 1.5 else '缩量' if vr < 0.7 else '正常'})")
    if tech.get("boll_position"):
        bp_map = {"above_upper": "突破上轨", "below_lower": "跌破下轨", "upper_half": "中上轨", "lower_half": "中下轨"}
        lines.append(f"布林位置: {bp_map.get(tech['boll_position'], tech['boll_position'])}")

    if quote:
        if quote.get("pe"):
            lines.append(f"PE: {quote['pe']}")
        if quote.get("pb"):
            lines.append(f"PB: {quote['pb']}")

    return "\n".join(lines)


async def _gather_eastmoney_context(symbols: list[str]) -> str:
    """Gather EastMoney AI SaaS data for analysis enrichment."""
    blocks = []
    em = EastMoneyClient()

    try:
        for symbol in symbols[:5]:
            q = await asyncio.to_thread(em_get_realtime_quote, symbol)
            if q and q.get("name"):
                em_chg = q.get("change_pct", 0)
                blocks.append(
                    f"- {q['name']}({symbol}): ¥{q.get('price', 'N/A')} "
                    f"涨跌{em_chg:+.2f}% 成交额{q.get('volume', 'N/A')}"
                )
    except Exception:
        pass

    try:
        changes = await asyncio.to_thread(get_stock_changes)
        if changes:
            hot = [c for c in changes[:10] if c.get("name")]
            if hot:
                blocks.append("\n异动监控:")
                for c in hot:
                    blocks.append(f"- {c.get('name', '?')}({c.get('code', '?')}): {c.get('type', '?')} {c.get('desc', '')}")
    except Exception:
        pass

    try:
        hot_data = await asyncio.to_thread(get_hot_tables)
        if hot_data:
            items = hot_data[:8]
            if items:
                blocks.append("\n龙虎榜:")
                for h in items:
                    blocks.append(f"- {h.get('name', '?')}({h.get('code', '?')}): 买入{h.get('buy', '?')} 卖出{h.get('sell', '?')}")
    except Exception:
        pass

    return "\n".join(blocks) if blocks else ""


async def deep_analysis(
    symbols: list[str],
    user_prefs: dict[str, Any] | None = None,
    news_items: list[dict] | None = None,
    portfolio_text: str = "",
    platform_names: str = "",
) -> dict[str, Any]:
    settings = load_settings()
    run_id = f"analysis-{uuid.uuid4().hex[:8]}"
    prefs = user_prefs or {}
    risk_level = prefs.get("risk_level", "conservative")
    watchlist = prefs.get("watchlist", [])
    sectors = prefs.get("sectors", [])

    quote_data = {}
    kline_data = {}
    tech_contexts = {}

    for symbol in symbols[:5]:
        quote = await fetch_realtime_quote(symbol)
        klines = await fetch_kline(symbol)
        if quote:
            quote_data[symbol] = quote
        if klines:
            kline_data[symbol] = klines
            tech_contexts[symbol] = _build_technical_context(klines, quote)

    em_context = ""
    try:
        em_context = await _gather_eastmoney_context(symbols)
    except Exception as e:
        logger.warning("EastMoney context gathering failed: %s", e)

    news_text = " ".join(
        n.get("title", "") + " " + (n.get("summary", "") or "")
        for n in (news_items or [])[:10]
    )
    sentiment_block = ""
    if news_text.strip():
        try:
            sent = await asyncio.to_thread(analyze_sentiment, news_text)
            sentiment_block = (
                f"市场情绪: {sent['category']} (得分{sent['score']:.1f})\n"
                f"正面词: {', '.join(w for w, _ in sent.get('positive_words', [])[:5])}\n"
                f"负面词: {', '.join(w for w, _ in sent.get('negative_words', [])[:5])}"
            )
        except Exception:
            sentiment_block = ""

    news_block = ""
    if news_items:
        news_block = "\n".join(
            f"- [{n.get('pub_date', '')}] {n['title']} ({n.get('query', '')})"
            for n in news_items[:10]
        )
    else:
        news_block = "（未获取到新闻）"

    portfolio_block = portfolio_text[:2000] if portfolio_text else "（未获取持仓信息）"

    stock_analysis_blocks = []
    for symbol in symbols[:5]:
        q = quote_data.get(symbol, {})
        t = tech_contexts.get(symbol, "数据不足")
        block = f"### {symbol} ({q.get('name', '未知')})\n{t}"
        if q.get("price"):
            block += f"\n实时价: ¥{q['price']}"
        if q.get("change_pct") is not None:
            block += f"  涨跌: {q['change_pct']}%"
        stock_analysis_blocks.append(block)

    stocks_text = "\n\n".join(stock_analysis_blocks) if stock_analysis_blocks else "（无实时数据）"

    em_block = ""
    if em_context:
        em_block = f"""## 东方财富实时数据
{em_context}
"""

    sentiment_section = ""
    if sentiment_block:
        sentiment_section = f"""## 市场情绪分析
{sentiment_block}
"""

    prompt = f"""你是「小土豆」AI 操盘手，现在进行深度选股分析。

## 用户配置
- 风险偏好: {risk_level}
- 自选股: {', '.join(watchlist) or '未设置'}
- 关注板块: {', '.join(sectors) or '未设置'}
- 平台: {platform_names}

{em_block}{sentiment_section}## 实时行情与技术指标
{stocks_text}

## 最新资讯
{news_block}

## 当前持仓
{portfolio_block}

## 深度分析要求

**你是一个有纪律的操盘手，每只推荐/操作的股票都必须给出完整理由。**

请输出 JSON：
{{
    "market_summary": "200字市场整体判断",
    "market_regime": "bull/bear/sideways/volatile",
    "stock_picks": [
        {{
            "symbol": "代码",
            "name": "名称",
            "action": "BUY/SELL/HOLD/WATCH",
            "confidence": 0.0-1.0,
            "reasoning": "必须至少3句话详细解释为什么选这只股。包含：1)技术面信号 2)基本面/消息面逻辑 3)板块/行业配合",
            "why_not_others": "为什么不是其他同板块股票？差异化优势在哪里？",
            "entry_price": "建议买入价位",
            "target_price": "目标价位",
            "stop_loss": "止损价位（必须设，低于此价无条件卖出）",
            "position_size": "建议仓位百分比（1-100%）",
            "time_horizon": "短线/中线/长线",
            "risk_reward": "风险收益比（如1:3）",
            "news_correlation": "与哪条新闻最相关",
            "catalysts": ["催化剂1", "催化剂2"],
            "risks": ["风险1", "风险2"],
            "monitor_signals": {{
                "add_conditions": "加仓条件",
                "exit_conditions": "卖出条件（含止损+止盈）",
                "red_flags": "出现什么信号必须立刻离场"
            }}
        }}
    ],
    "risk_warnings": ["系统性风险1", "风险2"],
    "action_plan": "今日操作建议（简洁版）",
    "position_sizing": {{
        "max_single_pct": 30,
        "recommended_cash_reserve_pct": 20,
        "reasoning": "仓位管理逻辑"
    }},
    "sell_strategy": {{
        "take_profit_rules": "分批止盈规则",
        "stop_loss_rules": "止损规则（硬止损+时间止损）",
        "trailing_stop": "移动止损策略"
    }}
}}

规则：
1. stock_picks 最多推荐 5 只股票
2. 每只股票的 reasoning 必须包含技术面、基本面、消息面三层逻辑
3. confidence < 0.65 的不做 BUY 推荐
4. 每只股票必须设止损价（硬止损，不允许"看情况"）
5. 必须给出 risk_reward 风险收益比
6. monitor_signals 必须明确什么信号出现就必须离场
7. position_sizing 必须给出仓位管理建议
8. sell_strategy 必须包含分批止盈和移动止损规则
9. 保守策略下单笔不超过总资产30%
10. 不编造未在数据/新闻中出现的事实"""

    result = await asyncio.to_thread(
        chat,
        prompt,
        system="你是专业量化操盘手「小土豆」，保守纪律优先，用中文输出。每只股票必须给出清晰的选股理由和退出策略。",
        settings=settings,
        max_tokens=4000,
        task="analysis",
    )

    if result.get("ok"):
        try:
            analysis = json.loads(result["content"])
            analysis["_metadata"] = {
                "run_id": run_id,
                "symbols_analyzed": symbols,
                "model": result.get("model"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data_sources": {
                    "quotes": len(quote_data),
                    "klines": len(kline_data),
                    "news": len(news_items) if news_items else 0,
                    "eastmoney": bool(em_context),
                    "sentiment": bool(sentiment_block),
                },
            }
            return {"ok": True, "analysis": analysis}
        except json.JSONDecodeError:
            return {"ok": True, "analysis_text": result["content"], "run_id": run_id}
    else:
        return {"ok": False, "error": result.get("error"), "run_id": run_id}


def format_trade_decision_for_pet(analysis_result: dict[str, Any]) -> str:
    if not analysis_result.get("ok"):
        return f"分析失败: {analysis_result.get('error', '未知错误')}"

    a = analysis_result.get("analysis", {})
    lines = ["📊 小土豆操盘分析", ""]

    if a.get("market_summary"):
        regime_map = {"bull": "牛市震荡", "bear": "熊市防守", "sideways": "横盘观望", "volatile": "高波动谨慎"}
        regime = regime_map.get(a.get("market_regime", ""), a.get("market_regime", ""))
        lines.append(f"【市场】{a['market_summary']}")
        if regime:
            lines.append(f"当前格局: {regime}")
        lines.append("")

    picks = a.get("stock_picks", [])
    if picks:
        lines.append("【选股推荐】")
        for i, p in enumerate(picks, 1):
            action_emoji = {"BUY": "🟢买入", "SELL": "🔴卖出", "HOLD": "🟡持有", "WATCH": "👀观察"}.get(p.get("action", ""), "⚪")
            conf = p.get("confidence", 0)
            lines.append(f"{i}. {action_emoji} {p.get('name', '')}({p.get('symbol', '')}) 置信度{conf:.0%}")
            lines.append(f"   ✦ 理由: {p.get('reasoning', '未说明')[:200]}")
            lines.append(f"   ✦ 建议价: {p.get('entry_price', '-')} → 目标: {p.get('target_price', '-')} | 止损: {p.get('stop_loss', '-')}")
            lines.append(f"   ✦ 仓位: {p.get('position_size', '-')} | 周期: {p.get('time_horizon', '-')} | 风险收益比: {p.get('risk_reward', '-')}")
            ms = p.get("monitor_signals", {})
            if ms.get("red_flags"):
                lines.append(f"   ✦ 离场信号: {ms['red_flags']}")
        lines.append("")

    ps = a.get("position_sizing", {})
    if ps:
        lines.append(f"【仓位管理】单笔≤{ps.get('max_single_pct', 30)}% 现金预留{ps.get('recommended_cash_reserve_pct', 20)}%")

    ss = a.get("sell_strategy", {})
    if ss:
        lines.append(f"【卖出策略】{ss.get('take_profit_rules', '')}")
        lines.append(f"   止损: {ss.get('stop_loss_rules', '')}")
        lines.append(f"   移动止损: {ss.get('trailing_stop', '')}")

    warnings = a.get("risk_warnings", [])
    if warnings:
        lines.append("")
        lines.append("⚠️ " + " | ".join(warnings[:3]))

    return "\n".join(lines)


def format_trade_signal_message(pick: dict[str, Any]) -> str:
    action = pick.get("action", "WATCH")
    if action not in ("BUY", "SELL"):
        return ""
    emoji = "🟢" if action == "BUY" else "🔴"
    name = pick.get("name", "")
    symbol = pick.get("symbol", "")
    entry = pick.get("entry_price", "")
    target = pick.get("target_price", "")
    stop = pick.get("stop_loss", "")
    conf = pick.get("confidence", 0)
    reasoning = pick.get("reasoning", "")[:150]

    lines = [
        f"{emoji} {'买入' if action == 'BUY' else '卖出'}信号",
        f"{name}({symbol}) 置信度{conf:.0%}",
        f"建议价: {entry} | 目标: {target} | 止损: {stop}",
        f"理由: {reasoning}",
    ]

    ms = pick.get("monitor_signals", {})
    if ms.get("exit_conditions"):
        lines.append(f"离场条件: {ms['exit_conditions']}")
    if ms.get("red_flags"):
        lines.append(f"危险信号: {ms['red_flags']}")

    return "\n".join(lines)