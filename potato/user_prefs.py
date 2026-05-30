"""User preference memory — remembers user's stock interests, sectors, and trading style.

Persisted to JSON. AI reads these preferences to:
1. Build personalized news queries
2. Adjust analysis aggressiveness
3. Focus on user's preferred sectors/stocks
4. Remember which platforms the user trades on
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("potato.user_prefs")

from potato.paths import DATA_DIR

DEFAULT_PREFS = {
    "sectors": [],
    "watchlist": [],
    "custom_queries": [],
    "risk_level": "",
    "max_single_trade_cny": None,
    "max_daily_trade_cny": None,
    "max_open_positions": None,
    "stop_loss_pct": None,
    "take_profit_pct": None,
    "max_consecutive_losses": 3,
    "preferred_markets": [],
    "language": "zh-CN",
    "daily_briefing_enabled": True,
    "auto_trade_enabled": False,
    "risk_confirmed": False,
    "notes": "",
    "updated_at": "",
}


class UserPrefs:
    """Read/write user preferences — persisted to data/user_prefs.json."""

    def __init__(self):
        self._path = DATA_DIR / "user_prefs.json"
        self._prefs: dict[str, Any] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                raw = self._path.read_text(encoding="utf-8")
                self._prefs = json.loads(raw)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("user_prefs load failed (%s), using defaults", exc)
                self._prefs = dict(DEFAULT_PREFS)
        else:
            self._prefs = dict(DEFAULT_PREFS)
        for k, v in DEFAULT_PREFS.items():
            self._prefs.setdefault(k, v)

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
        data = json.dumps(self._prefs, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(suffix=".json", dir=str(self._path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp, self._path)
        except BaseException:
            os.unlink(tmp) if os.path.exists(tmp) else None
            raise

    def get_all(self) -> dict[str, Any]:
        return dict(self._prefs)

    def get(self, key: str, default=None):
        return self._prefs.get(key, default)

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        for k, v in updates.items():
            if k in DEFAULT_PREFS:
                self._prefs[k] = v
        self._save()
        return self.get_all()

    def add_to_watchlist(self, symbol: str) -> list[str]:
        wl = self._prefs.get("watchlist", [])
        if symbol not in wl:
            wl.append(symbol)
            self._prefs["watchlist"] = wl
            self._save()
        return wl

    def remove_from_watchlist(self, symbol: str) -> list[str]:
        wl = self._prefs.get("watchlist", [])
        if symbol in wl:
            wl.remove(symbol)
            self._prefs["watchlist"] = wl
            self._save()
        return wl

    def add_sector(self, sector: str) -> list[str]:
        sectors = self._prefs.get("sectors", [])
        if sector not in sectors:
            sectors.append(sector)
            self._prefs["sectors"] = sectors
            self._save()
        return sectors

    def set_risk_level(self, level: str) -> str:
        _CN_MAP = {"保守": "conservative", "稳健": "moderate", "激进": "aggressive",
                    "保守型": "conservative", "稳健型": "moderate", "激进型": "aggressive"}
        level = _CN_MAP.get(level, level)
        if level in ("conservative", "moderate", "aggressive"):
            self._prefs["risk_level"] = level
            self._save()
        return self._prefs["risk_level"]

    def to_context_string(self) -> str:
        """Summary for AI system prompt."""
        lines = []
        if self._prefs.get("sectors"):
            lines.append(f"关注板块: {', '.join(self._prefs['sectors'])}")
        if self._prefs.get("watchlist"):
            lines.append(f"自选股: {', '.join(self._prefs['watchlist'])}")

        risk_confirmed = self._prefs.get("risk_confirmed", False)
        if risk_confirmed:
            rl = self._prefs.get("risk_level", "")
            rl_cn = {"conservative": "保守", "moderate": "稳健", "aggressive": "激进"}.get(rl, rl)
            lines.append(f"风险偏好: {rl_cn}（已确认）")
            single = self._prefs.get("max_single_trade_cny")
            daily = self._prefs.get("max_daily_trade_cny")
            positions = self._prefs.get("max_open_positions")
            sl = self._prefs.get("stop_loss_pct")
            tp = self._prefs.get("take_profit_pct")
            if single is not None: lines.append(f"单笔限额: ¥{single}")
            if daily is not None: lines.append(f"日限额: ¥{daily}")
            if positions is not None: lines.append(f"最多持仓: {positions}只")
            if sl is not None: lines.append(f"止损线: {float(sl)*100:.0f}%")
            if tp is not None: lines.append(f"止盈线: {float(tp)*100:.0f}%")
        else:
            lines.append("⚠️ 风控参数未设置——用户还没确认限额，你必须先问用户确认！")
            lines.append("请主动问用户：1) 单笔最多投多少？ 2) 每天最多投多少？ 3) 最多同时持几只股？ 4) 止损比例设多少？")
            lines.append("用户说了以后用 update_risk 设置并标记 risk_confirmed=true")

        lines.append(f"自动交易: {'开启' if self._prefs.get('auto_trade_enabled') else '关闭（仅分析建议）'}")
        return "\n".join(lines)
