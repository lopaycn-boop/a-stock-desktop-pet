"""Browser trading actions — AI-driven browser control for stock platforms.

小土豆 uses these actions to:
1. Log into user's stock platforms
2. Navigate to trading pages
3. Search for stocks
4. Read market data from the page
5. Execute buy/sell orders via browser UI
6. Take screenshots for AI analysis
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from potato.browser.engine import BrowserEngine, _PLAYWRIGHT_AVAILABLE
from potato.browser.platforms import PlatformConfig, PlatformRegistry
from potato.security import mask_secret

logger = logging.getLogger("potato.browser.actions")


class BrowserTrader:
    """High-level browser trading operations for AI agent use."""

    def __init__(self):
        self.engine = BrowserEngine.get()
        self.registry = PlatformRegistry()

    async def ensure_started(self, headless: bool = True):
        if not _PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("playwright not installed")
        await self.engine.start(headless=headless)

    async def login_platform(self, platform_id: str, credentials: dict[str, str] | None = None) -> dict[str, Any]:
        """Navigate to platform login page. If credentials provided, auto-fill.
        Otherwise, take screenshot so user can log in via desktop pet UI."""
        cfg = self.registry.get(platform_id)
        if not cfg:
            return {"ok": False, "error": f"Platform {platform_id} not configured"}

        nav = await self.engine.navigate(platform_id, cfg.login_url)
        if not nav["ok"]:
            return {"ok": False, "error": f"Cannot reach {cfg.login_url}", **nav}

        if credentials and cfg.login_fields and cfg.login_submit_selector:
            logger.info("Auto-login for %s ( credentials: %s)", platform_id,
                        {k: mask_secret(v) for k, v in credentials.items()})
            fields = {}
            for selector, cred_key in cfg.login_fields.items():
                if cred_key in credentials:
                    fields[selector] = credentials[cred_key]
            if fields:
                result = await self.engine.fill_and_submit(
                    platform_id, fields, cfg.login_submit_selector
                )
                return {"ok": True, "action": "auto_login", **result}

        screenshot = await self.engine.screenshot(platform_id)
        return {
            "ok": True,
            "action": "manual_login_needed",
            "url": nav["url"],
            "screenshot_b64": base64.b64encode(screenshot).decode() if screenshot else None,
            "hint": f"请在桌宠界面完成 {cfg.name} 登录",
        }

    async def check_login_status(self, platform_id: str) -> dict[str, Any]:
        """Check if user is logged in by navigating to portfolio page."""
        cfg = self.registry.get(platform_id)
        if not cfg:
            return {"ok": False, "logged_in": False, "error": "Platform not configured"}

        target = cfg.portfolio_url or cfg.url
        nav = await self.engine.navigate(platform_id, target)

        page_url = nav.get("url", "")
        title = nav.get("title", "")

        is_login_page = any(kw in page_url.lower() for kw in ["login", "sign-in", "signin", "passport"])
        logged_in = not is_login_page

        return {
            "ok": True,
            "logged_in": logged_in,
            "platform": cfg.name,
            "current_url": page_url,
            "title": title,
        }

    async def search_stock(self, platform_id: str, query: str) -> dict[str, Any]:
        """Search for a stock on the platform."""
        cfg = self.registry.get(platform_id)
        if not cfg:
            return {"ok": False, "error": "Platform not configured"}

        if cfg.search_selector:
            page = await self.engine.get_page(platform_id)
            await page.fill(cfg.search_selector, query)
            await page.keyboard.press("Enter")
            await page.wait_for_load_state("networkidle", timeout=10000)

        screenshot = await self.engine.screenshot(platform_id)
        page_text = await self.engine.get_page_text(platform_id)

        return {
            "ok": True,
            "query": query,
            "page_text_preview": page_text[:2000],
            "screenshot_b64": base64.b64encode(screenshot).decode() if screenshot else None,
        }

    async def read_page_for_ai(self, platform_id: str) -> dict[str, Any]:
        """Extract current page content for AI analysis — text + screenshot."""
        page_text = await self.engine.get_page_text(platform_id)
        screenshot = await self.engine.screenshot(platform_id)
        page = await self.engine.get_page(platform_id)
        url = page.url if page and not page.is_closed() else ""
        title = await page.title() if page and not page.is_closed() else ""

        return {
            "ok": True,
            "url": url,
            "title": title,
            "text_preview": page_text[:3000],
            "screenshot_b64": base64.b64encode(screenshot).decode() if screenshot else None,
        }

    async def navigate_to_trade(self, platform_id: str, symbol: str = "") -> dict[str, Any]:
        """Navigate to the trading page for a specific stock/market."""
        cfg = self.registry.get(platform_id)
        if not cfg:
            return {"ok": False, "error": "Platform not configured"}

        if cfg.trade_url and symbol:
            url = cfg.trade_url.format(symbol=symbol, market_id=symbol)
        elif cfg.portfolio_url:
            url = cfg.portfolio_url
        else:
            url = cfg.url

        return await self.engine.navigate(platform_id, url)

    async def execute_browser_trade(
        self,
        platform_id: str,
        action: str,
        symbol: str,
        amount: str,
        ai_instructions: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Execute a trade by following AI-generated browser instructions.

        ai_instructions is a list of steps like:
        [
            {"action": "navigate", "url": "..."},
            {"action": "click", "selector": "..."},
            {"action": "fill", "selector": "...", "value": "..."},
            {"action": "click", "selector": "#submit-order"},
            {"action": "wait", "seconds": "2"},
            {"action": "screenshot"},
        ]
        """
        results = []
        page = await self.engine.get_page(platform_id)

        for step in ai_instructions:
            step_action = step.get("action", "")
            try:
                if step_action == "navigate":
                    r = await self.engine.navigate(platform_id, step["url"])
                    results.append({"step": step_action, **r})

                elif step_action == "click":
                    r = await self.engine.click_element(platform_id, step["selector"])
                    results.append({"step": step_action, **r})

                elif step_action == "fill":
                    await page.fill(step["selector"], step["value"])
                    results.append({"step": step_action, "ok": True})

                elif step_action == "wait":
                    import asyncio
                    await asyncio.sleep(float(step.get("seconds", 1)))
                    results.append({"step": "wait", "ok": True})

                elif step_action == "screenshot":
                    shot = await self.engine.screenshot(platform_id)
                    results.append({
                        "step": "screenshot",
                        "ok": True,
                        "screenshot_b64": base64.b64encode(shot).decode() if shot else None,
                    })

                elif step_action == "read":
                    text = await self.engine.get_page_text(platform_id)
                    results.append({"step": "read", "ok": True, "text_preview": text[:2000]})

                else:
                    results.append({"step": step_action, "ok": False, "error": "unknown action"})

            except Exception as exc:
                results.append({"step": step_action, "ok": False, "error": str(exc)})
                break

        await self.engine.save_platform_state(platform_id)

        return {
            "ok": all(r.get("ok") for r in results),
            "trade": {"action": action, "symbol": symbol, "amount": amount},
            "steps_executed": len(results),
            "results": results,
        }

    async def get_portfolio_snapshot(self, platform_id: str) -> dict[str, Any]:
        """Navigate to portfolio and capture current holdings for AI analysis."""
        cfg = self.registry.get(platform_id)
        if not cfg or not cfg.portfolio_url:
            return {"ok": False, "error": "No portfolio URL configured"}

        await self.engine.navigate(platform_id, cfg.portfolio_url)
        return await self.read_page_for_ai(platform_id)

    async def close(self):
        await self.engine.stop()
