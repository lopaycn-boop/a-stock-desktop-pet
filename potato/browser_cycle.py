"""Browser-based trading cycle — AI analyzes, browser executes.

Two operating modes per platform:
  AUTONOMOUS: user gave credentials → 小土豆 logs in automatically + trades.
  ASSISTED:   no credentials → user logs in via desktop pet → 小土豆 operates.

Flow:
1. Check credentials plugin for each active platform
2. AUTONOMOUS platforms: auto-login with stored credentials
3. ASSISTED platforms: wait for user login via desktop pet
4. Fetch personalized news → AI analysis → execute trades
5. Report results to user via desktop pet
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from potato.analysis import (
    analyze_stocks,
    build_news_queries,
    fetch_stock_news,
    format_analysis_for_pet,
)
from potato.browser.actions import BrowserTrader
from potato.browser.engine import BrowserEngine
from potato.browser.platforms import PlatformRegistry
from potato.config import load_settings
from potato.credentials import CredentialsPlugin
from potato.db import Database
from potato.llm import chat
from potato.risk import RiskState, RiskValidator, TradeRequest
from potato.security import mask_secret
from potato.user_prefs import UserPrefs

logger = logging.getLogger("potato.browser_cycle")


def _load_risk_state(db: Database) -> RiskState:
    """Load today's risk state from DB for pre-trade validation."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state = RiskState(date=today)
    try:
        db_state = db.get_risk_state()
        state.total_traded_cny = Decimal(str(db_state.get("spent_cny", "0")))
        state.trade_count = int(db_state.get("trade_count", 0))
        state.circuit_breaker = bool(db_state.get("circuit_breaker", False))
    except Exception as exc:
        logger.warning("Could not load risk state from DB: %s", exc)
    return state


async def run_browser_cycle(run_id: str | None = None) -> dict[str, Any]:
    settings = load_settings()
    run_id = run_id or f"browser-{uuid.uuid4().hex[:8]}"
    prefs = UserPrefs()
    registry = PlatformRegistry()
    db = Database(settings)
    cred_plugin = CredentialsPlugin(settings)
    risk_validator = RiskValidator(settings, prefs)
    risk_state = _load_risk_state(db)
    logger.info("Risk limits: max_single=¥%.0f max_daily=¥%.0f max_positions=%d circuit_breaker=%s",
                risk_validator._limits["max_single_trade_cny"],
                risk_validator._limits["max_daily_trade_cny"],
                risk_validator._limits["max_open_positions"],
                risk_state.circuit_breaker)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "mode": "browser",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps": [],
        "analysis": None,
        "trades_executed": [],
        "errors": [],
        "status": "running",
    }

    browser_ok = BrowserEngine.available()

    try:
        db.init_schema()
        db.start_cycle(run_id)

        # Step 1: Check platforms
        platforms = registry.list_active()
        if not platforms:
            summary["steps"].append("no_platforms_configured")
            summary["status"] = "completed"
            summary["pet_message"] = (
                "你还没有配置任何交易平台哦~ 在桌宠里告诉我你用什么平台吧！\n"
                "可用平台: 东方财富、同花顺、雪球"
            )
            db.finish_cycle(run_id, "completed", summary)
            return summary

        platform_names = ", ".join(p.name for p in platforms)
        summary["steps"].append({"platforms": [p.platform_id for p in platforms]})

        # Step 2: Determine autonomous vs assisted per platform
        platform_modes: dict[str, str] = {}
        for p in platforms:
            cred = cred_plugin.get(p.platform_id)
            if cred and cred.autonomous and cred.fields:
                platform_modes[p.platform_id] = "autonomous"
            else:
                platform_modes[p.platform_id] = "assisted"

        summary["steps"].append({"platform_modes": platform_modes})

        # Step 3: Start browser, login to all platforms (skip if no playwright)
        login_status = {}
        if browser_ok:
            trader = BrowserTrader()
            await trader.ensure_started(headless=True)

            for platform in platforms:
                mode = platform_modes[platform.platform_id]
                cfg = registry.get(platform.platform_id)

                if mode == "autonomous":
                    credentials = cred_plugin.get_decoded_credentials(platform.platform_id)
                    login_result = await trader.login_platform(platform.platform_id, credentials)
                    if login_result.get("ok"):
                        cred_plugin.touch_used(platform.platform_id)
                        login_status[platform.platform_id] = {
                            "logged_in": True,
                            "mode": "autonomous",
                        }
                        summary["steps"].append({
                            "auto_login": platform.platform_id,
                            "ok": True,
                        })
                    else:
                        login_status[platform.platform_id] = {
                            "logged_in": False,
                            "mode": "autonomous_failed",
                            "error": login_result.get("error", ""),
                        }
                        summary["steps"].append({
                            "auto_login_failed": platform.platform_id,
                            "fallback": "assisted",
                        })
                        platform_modes[platform.platform_id] = "assisted"
                else:
                    login_result = await trader.login_platform(platform.platform_id)
                    is_login_page = "login" in login_result.get("url", "").lower() or "passport" in login_result.get("url", "").lower()
                    login_status[platform.platform_id] = {
                        "logged_in": not is_login_page,
                        "mode": "assisted",
                        "screenshot": bool(login_result.get("screenshot_b64")),
                    }
                    if is_login_page:
                        summary["steps"].append({
                            "login_needed": platform.platform_id,
                            "hint": f"请在桌宠里完成 {platform.name} 的登录，登录后小土豆会自动操盘",
                        })

            summary["steps"].append({"login_check": login_status})
        else:
            summary["steps"].append("browser_unavailable — analysis-only mode (install playwright for trading)")
            trader = None

        # Step 4: Fetch personalized news (run sync in executor to avoid blocking event loop)
        user_prefs = prefs.get_all()
        queries = build_news_queries(user_prefs)
        news = await asyncio.to_thread(fetch_stock_news, queries)
        summary["steps"].append({"news_fetched": len(news)})

        # Step 5: Read portfolio from logged-in platforms
        portfolio_texts = []
        if browser_ok and trader:
            for platform in platforms:
                if login_status.get(platform.platform_id, {}).get("logged_in"):
                    snapshot = await trader.get_portfolio_snapshot(platform.platform_id)
                    if snapshot.get("ok"):
                        portfolio_texts.append(
                            f"=== {platform.name} ({platform_modes[platform.platform_id]}) ===\n{snapshot.get('text_preview', '')}"
                        )
        combined_portfolio = "\n\n".join(portfolio_texts) or ""
        summary["steps"].append({"portfolio_read": len(portfolio_texts)})

        # Step 6: AI deep analysis
        mode_desc = "; ".join(f"{p.name}={platform_modes[p.platform_id]}" for p in platforms)
        analysis_result = await analyze_stocks(
            news=news,
            portfolio_text=combined_portfolio,
            user_prefs=user_prefs,
            platform_names=platform_names,
        )
        summary["analysis"] = analysis_result
        summary["steps"].append({"analysis_ok": analysis_result.get("ok")})

        # Step 7: Execute trades if auto_trade enabled (WITH RISK VALIDATION)
        if user_prefs.get("auto_trade_enabled") and analysis_result.get("ok") and browser_ok and trader:
            analysis = analysis_result.get("analysis", {})
            picks = analysis.get("stock_picks", [])
            for pick in picks:
                if pick.get("action") not in ("BUY", "SELL"):
                    continue

                # ---- RISK GATE: validate before execution ----
                entry_price = Decimal(str(pick.get("entry_price", 0) or 0))
                quantity = int(pick.get("quantity", 1) or 1)
                amount_cny = entry_price * quantity

                trade_req = TradeRequest(
                    action=pick["action"],
                    symbol=pick.get("symbol", ""),
                    name=pick.get("name", ""),
                    price=entry_price,
                    quantity=quantity,
                    amount_cny=amount_cny,
                    confidence=Decimal(str(pick.get("confidence", 0) or 0)),
                    reasoning=pick.get("reasoning", ""),
                )
                verdict = risk_validator.validate_trade(trade_req, risk_state)

                if not verdict.allowed:
                    logger.warning("TRADE BLOCKED: %s %s — %s", trade_req.action, trade_req.symbol, verdict.reason)
                    summary["trades_executed"].append({
                        "ok": False,
                        "symbol": trade_req.symbol,
                        "action": trade_req.action,
                        "blocked": True,
                        "reason": verdict.reason,
                    })
                    db.record_decision({
                        "run_id": run_id,
                        "action": f"BLOCKED_{trade_req.action}",
                        "token_id": trade_req.symbol,
                        "condition_id": trade_req.name,
                        "price": float(trade_req.price),
                        "size": float(trade_req.confidence),
                        "reasoning": f"RISK_BLOCKED: {verdict.reason}",
                        "model": settings.llm_model,
                    })
                    continue

                if verdict.warnings:
                    for w in verdict.warnings:
                        logger.warning("Trade warning: %s", w)

                trade_result = await _execute_ai_trade(
                    trader=trader,
                    platforms=platforms,
                    pick=pick,
                    settings=settings,
                    run_id=run_id,
                    platform_modes=platform_modes,
                )
                summary["trades_executed"].append(trade_result)

                # Update risk state after trade
                if trade_result.get("ok"):
                    risk_state.total_traded_cny += amount_cny
                    risk_state.trade_count += 1
                    risk_state.consecutive_losses = 0
                    db.record_spend(amount_cny)
                else:
                    risk_state.consecutive_losses += 1
                    if risk_state.consecutive_losses >= risk_validator.get_limits()["max_consecutive_losses"]:
                        risk_state.circuit_breaker = True
                        db.set_circuit_breaker(True)
                        logger.error("CIRCUIT BREAKER TRIGGERED after %d consecutive losses", risk_state.consecutive_losses)

                db.record_decision({
                    "run_id": run_id,
                    "action": pick["action"],
                    "token_id": pick.get("symbol", ""),
                    "condition_id": pick.get("name", ""),
                    "price": float(pick.get("entry_price", 0) or 0),
                    "size": float(pick.get("confidence", 0) or 0),
                    "reasoning": pick.get("reasoning", ""),
                    "model": settings.llm_model,
                })
        else:
            if not browser_ok:
                summary["steps"].append("auto_trade_skipped — playwright not installed (analysis-only)")
            elif not user_prefs.get("auto_trade_enabled"):
                summary["steps"].append("auto_trade_disabled — analysis only")
            else:
                summary["steps"].append("auto_trade_skipped — analysis failed")

        # Step 8: Generate pet briefing
        pet_msg = format_analysis_for_pet(analysis_result)
        if summary["trades_executed"]:
            executed = len([t for t in summary["trades_executed"] if t.get("ok")])
            pet_msg += f"\n\n已执行 {executed} 笔交易"

        # Add credential status to briefing
        auto_platforms = [p.name for p in platforms if platform_modes.get(p.platform_id) == "autonomous"]
        assisted_needed = [
            p.name for p in platforms
            if platform_modes.get(p.platform_id) == "assisted"
            and not login_status.get(p.platform_id, {}).get("logged_in")
        ]
        if auto_platforms:
            pet_msg += f"\n🔑 自主操盘: {', '.join(auto_platforms)}"
        if assisted_needed:
            pet_msg += f"\n🔐 需要登录: {', '.join(assisted_needed)}（登录后小土豆自动接管）"

        summary["pet_message"] = pet_msg
        summary["platform_modes"] = platform_modes

        summary["status"] = "completed"
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.finish_cycle(run_id, "completed", summary)

    except Exception as exc:
        logger.exception("Browser cycle failed")
        summary["status"] = "failed"
        summary["errors"].append(str(exc))
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        try:
            db.finish_cycle(run_id, "failed", summary)
        except Exception:
            pass

    return summary


async def _execute_ai_trade(
    trader: BrowserTrader,
    platforms: list,
    pick: dict[str, Any],
    settings,
    run_id: str,
    platform_modes: dict[str, str] | None = None,
) -> dict[str, Any]:
    symbol = pick.get("symbol", "")
    action = pick.get("action", "HOLD")
    platform_modes = platform_modes or {}
    platform = platforms[0] if platforms else None

    if not platform:
        return {"ok": False, "symbol": symbol, "error": "no_platform"}

    mode = platform_modes.get(platform.platform_id, "assisted")
    mode_hint = "（自主模式，小土豆全权操作）" if mode == "autonomous" else "（协助模式，用户已登录）"

    prompt = f"""你需要在 {platform.name} ({platform.url}) 上执行以下交易{mode_hint}：
- 操作: {action}
- 股票: {symbol} ({pick.get('name', '')})
- 建议价格: {pick.get('entry_price', '市价')}

请生成浏览器操作步骤（JSON 数组），每一步是：
{{"action": "navigate/click/fill/wait/screenshot/read", "selector": "CSS选择器", "value": "填入值", "url": "目标URL"}}

注意：
1. 先导航到该股票的交易页面
2. 在买入/卖出框中填写数量和价格
3. 点击确认按钮
4. 等待并截图确认

请返回纯 JSON 数组，不要其他文字。"""

    result = await asyncio.to_thread(
        chat,
        prompt,
        system="你是浏览器自动化专家，生成精确的 CSS 选择器和操作步骤。只返回 JSON 数组。",
        settings=settings,
        max_tokens=1000,
        task="chat",
    )

    if not result.get("ok"):
        return {"ok": False, "symbol": symbol, "error": result.get("error")}

    try:
        instructions = json.loads(result["content"])
        if not isinstance(instructions, list):
            instructions = []
    except json.JSONDecodeError:
        return {"ok": False, "symbol": symbol, "error": "AI returned invalid JSON instructions"}

    if not instructions:
        return {"ok": False, "symbol": symbol, "error": "no_instructions_generated"}

    trade_result = await trader.execute_browser_trade(
        platform_id=platform.platform_id,
        action=action,
        symbol=symbol,
        amount=str(pick.get("entry_price", "")),
        ai_instructions=instructions,
    )

    return {**trade_result, "symbol": symbol, "mode": mode, "pick": pick}
