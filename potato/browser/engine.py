"""Browser automation engine using Playwright.

Core capability: 小土豆 controls a real browser to log into stock/prediction
platforms and execute trades on behalf of the user.  The desktop pet (Electron)
grants computer permissions; this module drives the actual browser session.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("potato.browser")

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "browser_profiles"

try:
    from playwright.async_api import Browser, BrowserContext, Page, async_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    Browser = None  # type: ignore[assignment,misc]
    BrowserContext = None  # type: ignore[assignment,misc]
    Page = None  # type: ignore[assignment,misc]
    async_playwright = None  # type: ignore[assignment]


class BrowserEngine:
    """Singleton browser controller — one Chromium instance shared across platforms."""

    _instance: Optional["BrowserEngine"] = None

    def __init__(self):
        self._pw = None
        self._browser: Optional[Browser] = None  # type: ignore[valid-type]
        self._contexts: dict[str, BrowserContext] = {}  # type: ignore[valid-type]
        self._pages: dict[str, Page] = {}  # type: ignore[valid-type]

    @classmethod
    def get(cls) -> "BrowserEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def available(cls) -> bool:
        if not _PLAYWRIGHT_AVAILABLE:
            return False
        try:
            import subprocess
            result = subprocess.run(
                ["python", "-m", "playwright", "install", "--dry-run", "chromium"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return _PLAYWRIGHT_AVAILABLE

    async def start(self, headless: bool = True) -> None:
        if not _PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("playwright not installed — run: pip install playwright && playwright install chromium")
        if self._browser:
            return
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        logger.info("Browser engine started (headless=%s)", headless)

    async def stop(self) -> None:
        for ctx in self._contexts.values():
            await ctx.close()
        self._contexts.clear()
        self._pages.clear()
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
        logger.info("Browser engine stopped")

    async def get_platform_context(self, platform_id: str) -> BrowserContext:
        """Get or create a persistent browser context for a platform.

        Each platform gets its own context with isolated cookies/storage so
        login sessions are preserved across cycles.
        """
        if platform_id in self._contexts:
            return self._contexts[platform_id]

        profile_dir = DATA_DIR / platform_id
        profile_dir.mkdir(parents=True, exist_ok=True)

        ctx = await self._browser.new_context(
            storage_state=str(profile_dir / "state.json")
            if (profile_dir / "state.json").exists()
            else None,
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._contexts[platform_id] = ctx
        logger.info("Browser context created for platform: %s", platform_id)
        return ctx

    async def save_platform_state(self, platform_id: str) -> None:
        """Persist cookies/localStorage so login survives restarts."""
        ctx = self._contexts.get(platform_id)
        if not ctx:
            return
        profile_dir = DATA_DIR / platform_id
        profile_dir.mkdir(parents=True, exist_ok=True)
        await ctx.storage_state(path=str(profile_dir / "state.json"))
        logger.info("Saved browser state for %s", platform_id)

    async def get_page(self, platform_id: str) -> Page:
        """Get or create a page for a platform context."""
        if platform_id in self._pages:
            page = self._pages[platform_id]
            if not page.is_closed():
                return page

        ctx = await self.get_platform_context(platform_id)
        page = await ctx.new_page()
        self._pages[platform_id] = page
        return page

    async def screenshot(self, platform_id: str) -> bytes | None:
        """Take a screenshot of the current platform page (for AI vision)."""
        page = self._pages.get(platform_id)
        if not page or page.is_closed():
            return None
        return await page.screenshot(type="jpeg", quality=70)

    async def navigate(self, platform_id: str, url: str) -> dict[str, Any]:
        page = await self.get_page(platform_id)
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return {
            "ok": resp is not None and resp.ok if resp else False,
            "url": page.url,
            "title": await page.title(),
        }

    async def fill_and_submit(
        self,
        platform_id: str,
        fields: dict[str, str],
        submit_selector: str,
    ) -> dict[str, Any]:
        """Fill form fields and click submit — used for login forms."""
        page = await self.get_page(platform_id)
        for selector, value in fields.items():
            await page.fill(selector, value)
        await page.click(submit_selector)
        await page.wait_for_load_state("networkidle", timeout=15000)
        await self.save_platform_state(platform_id)
        return {"ok": True, "url": page.url, "title": await page.title()}

    async def click_element(self, platform_id: str, selector: str) -> dict[str, Any]:
        page = await self.get_page(platform_id)
        await page.click(selector, timeout=10000)
        return {"ok": True, "url": page.url}

    async def get_page_text(self, platform_id: str) -> str:
        """Extract visible text from current page — for AI to analyze."""
        page = self._pages.get(platform_id)
        if not page or page.is_closed():
            return ""
        return await page.inner_text("body")

    async def evaluate_js(self, platform_id: str, script: str) -> Any:
        """Run JavaScript in the platform page context."""
        page = self._pages.get(platform_id)
        if not page or page.is_closed():
            return None
        return await page.evaluate(script)
