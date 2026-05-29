from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from potato.config import load_settings
from potato.db import Database

logger = logging.getLogger("potato.cycle")


def _decision(settings, **fields: Any) -> dict[str, Any]:
    fields.setdefault("model", settings.llm_model)
    return fields


def run_cycle(run_id: str | None = None) -> dict[str, Any]:
    settings = load_settings()
    run_id = run_id or f"astock-{uuid.uuid4().hex[:12]}"
    db = Database(settings)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "backend": db.backend,
        "trading_mode": settings.trading_mode,
        "dry_run": settings.dry_run,
        "llm_model": settings.llm_model,
        "steps": [],
        "actions": [],
        "errors": [],
    }

    try:
        db.init_schema()
        db.start_cycle(run_id)
        summary["steps"].append("cycle_started")

        loop = asyncio.new_event_loop()
        try:
            from potato.browser_cycle import run_browser_cycle

            result = loop.run_until_complete(run_browser_cycle(run_id=run_id))
        finally:
            loop.close()

        summary["steps"].extend(result.get("steps", []))
        summary["actions"].extend(result.get("trades_executed", []))
        summary["analysis"] = result.get("analysis")
        summary["pet_message"] = result.get("pet_message", "")
        summary["status"] = result.get("status", "completed")

        db.record_decision(
            _decision(
                settings,
                run_id=run_id,
                action="CYCLE",
                reasoning=f"browser cycle {summary['status']}",
            )
        )

        db.finish_cycle(run_id, summary["status"], summary)
        _notify_cycle(summary)
        return summary
    except Exception as exc:
        summary["status"] = "failed"
        summary["errors"].append(str(exc)[:200])
        try:
            db.finish_cycle(run_id, "failed", summary)
        except Exception:
            pass
        _notify_cycle(summary)
        return summary


def _notify_cycle(summary: dict[str, Any]) -> None:
    try:
        from potato.notifications import BotNotifier

        result = BotNotifier().notify_cycle(summary)
        tg = (result.get("channels") or {}).get("telegram") or {}
        if tg and not tg.get("ok") and not tg.get("skipped"):
            logger.warning("Telegram notify failed: %s", tg)
    except Exception as exc:
        logger.warning("Notify cycle failed: %s", exc)


def main() -> int:
    run_id = None
    if len(sys.argv) > 2 and sys.argv[1] == "--run-id":
        run_id = sys.argv[2]
    result = run_cycle(run_id)
    logger.info("Cycle %s status=%s", result.get("run_id"), result.get("status"))
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
