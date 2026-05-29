"""Activate Telegram / DingTalk / Feishu bots from app_secrets."""

from __future__ import annotations

import json
from typing import Any

import httpx

from potato.config import load_settings
from potato.notifications import BotNotifier, is_live_secret, upsert_bot_secret


def feishu_tenant_token(app_id: str, app_secret: str, api_base: str) -> dict[str, Any]:
    base = api_base.rstrip("/")
    try:
        resp = httpx.post(
            f"{base}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=30.0,
        )
        data = resp.json()
        if data.get("code") != 0:
            return {"ok": False, "error": data.get("msg", resp.text), "code": data.get("code")}
        return {"ok": True, "expire": data.get("expire")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def activate_bots(*, send_test: bool = True) -> dict[str, Any]:
    """Enable notifications, start Telegram poller, verify Feishu credentials."""
    upsert_bot_secret("POTATO_NOTIFY_ENABLED", "true")

    settings = load_settings()
    result: dict[str, Any] = {"ok": True, "steps": [], "bots": BotNotifier().channel_status()}

    # Telegram
    from potato.telegram_bot import get_telegram_runner, start_telegram_runner

    if is_live_secret(settings.telegram_bot_token):
        get_telegram_runner().delete_webhook()
        if not is_live_secret(settings.telegram_chat_id):
            discover = BotNotifier().telegram_discover_chat_id()
            result["steps"].append({"telegram_discover": discover})
            if discover.get("ok"):
                upsert_bot_secret("TELEGRAM_CHAT_ID", discover["chat_id"])
        runner = start_telegram_runner()
        result["steps"].append({"telegram_runner": runner})
        me = BotNotifier().telegram_get_me()
        result["telegram_bot"] = me.get("result")
    else:
        result["steps"].append({"telegram": "skipped — TELEGRAM_BOT_TOKEN not in DB"})

    # Feishu — verify app credentials
    settings = load_settings()
    if is_live_secret(settings.feishu_app_id) and is_live_secret(settings.feishu_app_secret):
        token_check = feishu_tenant_token(
            settings.feishu_app_id,
            settings.feishu_app_secret,
            settings.feishu_api_base,
        )
        result["steps"].append({"feishu_token": {"ok": token_check.get("ok"), "error": token_check.get("error")}})
        if token_check.get("ok") and not is_live_secret(settings.feishu_webhook_url):
            if not is_live_secret(settings.feishu_receive_id):
                result["steps"].append(
                    {
                        "feishu_send": "skipped — set FEISHU_RECEIVE_ID (chat open_id) or FEISHU_WEBHOOK_URL",
                        "hint": "飞书开放平台 → 事件订阅/机器人 → 获取群 chat_id 或配置 webhook",
                    }
                )
    else:
        result["steps"].append({"feishu": "skipped — FEISHU_APP_ID/SECRET not in DB"})

    result["bots"] = BotNotifier().channel_status()

    if send_test:
        test = BotNotifier().notify("🥔 小土豆机器人已激活 — 测试通知")
        result["test_notify"] = test

    active = []
    bots = result["bots"]
    if bots["telegram"].get("configured"):
        active.append("telegram")
    if bots["dingtalk"].get("configured"):
        active.append("dingtalk")
    if bots["feishu"].get("configured"):
        active.append("feishu")
    result["active_channels"] = active
    result["ok"] = True
    return result


def seed_and_activate_local(items: dict[str, str], *, send_test: bool = False) -> dict[str, Any]:
    """Write secrets to DB then activate (for local scripts)."""
    saved = []
    for key, value in items.items():
        if value:
            upsert_bot_secret(key, value.strip())
            saved.append(key)
    out = activate_bots(send_test=send_test)
    out["saved_keys"] = saved
    return out
