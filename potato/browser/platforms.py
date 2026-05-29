"""Platform registry — remembers which A-stock trading platforms the user trades on.

Each platform has login instructions, trading page selectors, and AI-readable
page structure so 小土豆 can navigate and operate autonomously.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("potato.browser.platforms")

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass
class PlatformConfig:
    """Configuration for a single trading platform."""
    platform_id: str
    name: str
    url: str
    login_url: str
    login_fields: dict[str, str] = field(default_factory=dict)
    login_submit_selector: str = ""
    portfolio_url: str = ""
    trade_url: str = ""
    search_selector: str = ""
    enabled: bool = True
    notes: str = ""


BUILTIN_PLATFORMS: dict[str, PlatformConfig] = {
    "eastmoney": PlatformConfig(
        platform_id="eastmoney",
        name="东方财富",
        url="https://www.eastmoney.com",
        login_url="https://passport2.eastmoney.com/pub/login",
        login_fields={"input[name='username']": "account", "input[name='password']": "password"},
        login_submit_selector="button.btn-login",
        portfolio_url="https://trade.eastmoney.com",
        search_selector="input.search-input",
        notes="A股/基金/ETF在线交易",
    ),
    "tonghuashun": PlatformConfig(
        platform_id="tonghuashun",
        name="同花顺",
        url="https://www.10jqka.com.cn",
        login_url="https://home.10jqka.com.cn/login",
        login_fields={"input[name='account']": "account", "input[name='password']": "password"},
        login_submit_selector="button.login-btn",
        portfolio_url="https://stockpage.10jqka.com.cn/realHead_v8.html",
        search_selector="#search-input",
        notes="A股行情/交易/数据终端",
    ),
    "xueqiu": PlatformConfig(
        platform_id="xueqiu",
        name="雪球",
        url="https://xueqiu.com",
        login_url="https://xueqiu.com",
        login_fields={"input[name='username']": "account", "input[name='password']": "password"},
        login_submit_selector="button.btn-login",
        portfolio_url="https://xueqiu.com/performance",
        search_selector="input.search__input",
        notes="股票社区 + 模拟/实盘组合",
    ),
}


class PlatformRegistry:
    """Manages user's active trading platforms — persisted to JSON."""

    def __init__(self):
        self._path = DATA_DIR / "user_platforms.json"
        self._platforms: dict[str, PlatformConfig] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for pid, data in raw.items():
                self._platforms[pid] = PlatformConfig(**data)
        logger.info("Loaded %d user platforms", len(self._platforms))

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {pid: asdict(p) for pid, p in self._platforms.items()}
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_platform(self, platform_id: str, **overrides) -> PlatformConfig:
        """Add a platform from builtins or custom config."""
        if platform_id in BUILTIN_PLATFORMS:
            cfg = copy.deepcopy(BUILTIN_PLATFORMS[platform_id])
            for k, v in overrides.items():
                if hasattr(cfg, k):
                    object.__setattr__(cfg, k, v)
            self._platforms[platform_id] = cfg
        else:
            self._platforms[platform_id] = PlatformConfig(
                platform_id=platform_id,
                name=overrides.get("name", platform_id),
                url=overrides.get("url", ""),
                login_url=overrides.get("login_url", ""),
                **{k: v for k, v in overrides.items() if k not in ("name", "url", "login_url")},
            )
        self._save()
        logger.info("Platform added: %s", platform_id)
        return self._platforms[platform_id]

    def remove_platform(self, platform_id: str) -> bool:
        if platform_id in self._platforms:
            del self._platforms[platform_id]
            self._save()
            return True
        return False

    def get(self, platform_id: str) -> PlatformConfig | None:
        return self._platforms.get(platform_id)

    def list_active(self) -> list[PlatformConfig]:
        return [p for p in self._platforms.values() if p.enabled]

    def list_all_builtin(self) -> dict[str, dict[str, str]]:
        return {pid: {"name": p.name, "notes": p.notes} for pid, p in BUILTIN_PLATFORMS.items()}

    def to_context_string(self) -> str:
        """Generate a summary for AI system prompt injection."""
        if not self._platforms:
            return "用户未配置任何交易平台"
        lines = []
        for p in self._platforms.values():
            status = "已启用" if p.enabled else "已禁用"
            lines.append(f"- {p.name} ({p.platform_id}): {p.url} [{status}]")
        return "\n".join(lines)
