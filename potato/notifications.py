"""Telegram / DingTalk / Feishu bot notifications — secrets from app_secrets."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
from typing import Any

import httpx

from potato.config import Settings, load_settings

logger = logging.getLogger("potato.notify")

PLACEHOLDER_PREFIX = "REPLACE_WITH_"


def is_live_secret(value: str) -> bool:
    v = (value or "").strip()
    return bool(v) and not v.startswith(PLACEHOLDER_PREFIX)


def _mask_token(token: str) -> str:
    if len(token) <= 10:
        return "***"
    return f"{token[:6]}...{token[-4:]}"


def format_cycle_message(summary: dict[str, Any]) -> str:
    status = summary.get("status", "unknown")
    run_id = summary.get("run_id", "-")
    mode = summary.get("trading_mode", "-")
    dry = summary.get("dry_run", True)
    actions = summary.get("actions") or []
    errors = summary.get("errors") or []
    risk = summary.get("risk_state") or {}

    lines = [
        "🥔 小土豆 A股操盘",
        f"状态: {status}",
        f"run_id: {run_id}",
        f"模式: {mode} ({'模拟' if dry else '实盘'})",
        f"动作数: {len(actions)}",
    ]
    for act in actions[:5]:
        if isinstance(act, dict):
            action_str = act.get('action', '?')
            symbol = act.get('symbol', act.get('token_id', ''))[:16]
            lines.append(f"  · {action_str} {symbol}")
    if len(actions) > 5:
        lines.append(f"  · ... 另有 {len(actions) - 5} 条")
    if risk:
        lines.append(
            f"风控: 日额 {risk.get('spent_cny', '?')} / 交易数 {risk.get('trade_count', '?')} / 熔断 {'是' if risk.get('circuit_breaker') else '否'}"
        )
    if errors:
        lines.append(f"错误: {errors[0][:200]}")
    return "\n".join(lines)


def format_intel_message(intel: dict[str, Any]) -> str:
    lines = [
        "📰 小土豆 · 每日资讯渗透简报",
        f"run_id: {intel.get('run_id', '-')}",
        f"扫描市场: {intel.get('markets_scanned', 0)} | 策略候选: {intel.get('candidates', 0)}",
        f"资讯条数: {len(intel.get('headlines') or [])}",
        "",
        intel.get("analysis") or intel.get("error") or "（无分析内容）",
    ]
    text = "\n".join(lines)
    if len(text) > 3500:
        text = text[:3490] + "\n…"
    return text


class BotNotifier:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()

    def channel_status(self) -> dict[str, Any]:
        s = self.settings
        return {
            "enabled": s.notify_enabled,
            "channels": s.notify_channels,
            "telegram": {
                "configured": is_live_secret(s.telegram_bot_token) and is_live_secret(s.telegram_chat_id),
                "token_set": is_live_secret(s.telegram_bot_token),
                "chat_id_set": is_live_secret(s.telegram_chat_id),
            },
            "dingtalk": {
                "configured": is_live_secret(s.dingtalk_webhook_url),
                "webhook_set": is_live_secret(s.dingtalk_webhook_url),
                "secret_set": is_live_secret(s.dingtalk_secret),
            },
            "feishu": {
                "configured": self._feishu_ready(),
                "webhook_set": is_live_secret(s.feishu_webhook_url),
                "app_id_set": is_live_secret(s.feishu_app_id),
                "app_secret_set": is_live_secret(s.feishu_app_secret),
                "receive_id_set": is_live_secret(s.feishu_receive_id),
            },
        }

    def _feishu_ready(self) -> bool:
        s = self.settings
        if is_live_secret(s.feishu_webhook_url):
            return True
        return (
            is_live_secret(s.feishu_app_id)
            and is_live_secret(s.feishu_app_secret)
            and is_live_secret(s.feishu_receive_id)
        )

    def notify(self, text: str) -> dict[str, Any]:
        if not self.settings.notify_enabled:
            return {"ok": False, "skipped": True, "reason": "POTATO_NOTIFY_ENABLED=false"}

        results: dict[str, Any] = {"ok": True, "channels": {}}
        for channel in self.settings.notify_channels:
            name = channel.strip().lower()
            if name == "telegram":
                results["channels"]["telegram"] = self._send_telegram(text)
            elif name == "dingtalk":
                results["channels"]["dingtalk"] = self._send_dingtalk(text)
            elif name in {"feishu", "lark"}:
                results["channels"]["feishu"] = self._send_feishu(text)
        sent = [k for k, v in results["channels"].items() if v.get("ok")]
        skipped = [k for k, v in results["channels"].items() if v.get("skipped")]
        results["sent"] = sent
        results["skipped"] = skipped
        results["ok"] = bool(sent) or bool(skipped)
        return results

    def notify_cycle(self, summary: dict[str, Any]) -> dict[str, Any]:
        return self.notify(format_cycle_message(summary))

    def _send_telegram(self, text: str) -> dict[str, Any]:
        token = self.settings.telegram_bot_token
        chat_id = self.settings.telegram_chat_id
        if not is_live_secret(token):
            return {"ok": False, "skipped": True, "reason": "TELEGRAM_BOT_TOKEN placeholder or empty"}
        if not is_live_secret(chat_id):
            return {"ok": False, "skipped": True, "reason": "TELEGRAM_CHAT_ID placeholder or empty"}
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            resp = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=30.0)
            data = resp.json()
            if not data.get("ok"):
                return {"ok": False, "error": data.get("description", resp.text)}
            return {"ok": True, "message_id": data.get("result", {}).get("message_id")}
        except Exception as exc:
            logger.warning("Telegram send failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def _send_dingtalk(self, text: str) -> dict[str, Any]:
        webhook = self.settings.dingtalk_webhook_url
        if not is_live_secret(webhook):
            return {"ok": False, "skipped": True, "reason": "DINGTALK_WEBHOOK_URL placeholder or empty"}
        url = webhook
        secret = self.settings.dingtalk_secret
        if is_live_secret(secret):
            ts = str(round(time.time() * 1000))
            string_to_sign = f"{ts}\n{secret}"
            sign = urllib.parse.quote_plus(
                base64.b64encode(
                    hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
                ).decode("utf-8")
            )
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}timestamp={ts}&sign={sign}"
        try:
            resp = httpx.post(url, json={"msgtype": "text", "text": {"content": text}}, timeout=30.0)
            data = resp.json()
            if data.get("errcode", 0) != 0:
                return {"ok": False, "error": data.get("errmsg", resp.text)}
            return {"ok": True}
        except Exception as exc:
            logger.warning("DingTalk send failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def _send_feishu(self, text: str) -> dict[str, Any]:
        webhook = self.settings.feishu_webhook_url
        if is_live_secret(webhook):
            try:
                resp = httpx.post(
                    webhook,
                    json={"msg_type": "text", "content": {"text": text}},
                    timeout=30.0,
                )
                data = resp.json()
                code = data.get("code", data.get("StatusCode", 0))
                if code not in (0, 200):
                    return {"ok": False, "error": data.get("msg", data.get("StatusMessage", resp.text))}
                return {"ok": True, "mode": "webhook"}
            except Exception as exc:
                logger.warning("Feishu webhook send failed: %s", exc)
                return {"ok": False, "error": str(exc)}

        app_id = self.settings.feishu_app_id
        app_secret = self.settings.feishu_app_secret
        receive_id = self.settings.feishu_receive_id
        if not (is_live_secret(app_id) and is_live_secret(app_secret) and is_live_secret(receive_id)):
            return {
                "ok": False,
                "skipped": True,
                "reason": "FEISHU_WEBHOOK_URL or (APP_ID+SECRET+RECEIVE_ID) not configured",
            }

        from potato.bot_activation import feishu_tenant_token

        token_result = feishu_tenant_token(app_id, app_secret, self.settings.feishu_api_base)
        if not token_result.get("ok"):
            return {"ok": False, "error": token_result.get("error", "tenant token failed")}

        base = self.settings.feishu_api_base.rstrip("/")
        token = token_result["tenant_access_token"]
        id_type = os.getenv("FEISHU_RECEIVE_ID_TYPE", "").strip()
        if not id_type:
            if receive_id.startswith("ou_"):
                id_type = "open_id"
            else:
                id_type = "chat_id"
        try:
            resp = httpx.post(
                f"{base}/open-apis/im/v1/messages",
                params={"receive_id_type": id_type},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": receive_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": text}, ensure_ascii=False),
                },
                timeout=30.0,
            )
            data = resp.json()
            if data.get("code") != 0:
                return {"ok": False, "error": data.get("msg", resp.text), "code": data.get("code")}
            return {"ok": True, "mode": "app_api", "message_id": (data.get("data") or {}).get("message_id")}
        except Exception as exc:
            logger.warning("Feishu app send failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def telegram_get_me(self) -> dict[str, Any]:
        token = self.settings.telegram_bot_token
        if not is_live_secret(token):
            return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}
        try:
            resp = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=30.0)
            return resp.json()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def telegram_discover_chat_id(self) -> dict[str, Any]:
        """Read getUpdates; return latest chat id (clears webhook first)."""
        token = self.settings.telegram_bot_token
        if not is_live_secret(token):
            return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}
        try:
            from potato.telegram_bot import get_telegram_runner

            get_telegram_runner().delete_webhook()
            resp = httpx.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"limit": 20},
                timeout=30.0,
            )
            data = resp.json()
            if not data.get("ok"):
                return {"ok": False, "error": data.get("description", "getUpdates failed")}
            updates = data.get("result") or []
            for item in reversed(updates):
                msg = item.get("message") or item.get("edited_message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                if chat_id is not None:
                    return {
                        "ok": True,
                        "chat_id": str(chat_id),
                        "username": chat.get("username"),
                        "first_name": chat.get("first_name"),
                        "text": msg.get("text"),
                    }
            return {
                "ok": False,
                "error": "没有收到消息 — 请在 Telegram 打开机器人，发送 /start 后再试",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def telegram_set_webhook(self, public_base_url: str) -> dict[str, Any]:
        token = self.settings.telegram_bot_token
        if not is_live_secret(token):
            return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}
        webhook_url = public_base_url.rstrip("/") + "/api/bots/telegram/webhook"
        import os
        secret_token = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
        payload: dict[str, Any] = {"url": webhook_url, "allowed_updates": ["message"]}
        if secret_token:
            payload["secret_token"] = secret_token
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/setWebhook",
                json=payload,
                timeout=30.0,
            )
            data = resp.json()
            return {"ok": bool(data.get("ok")), "webhook_url": webhook_url, "telegram": data}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


def ensure_bot_placeholders(store) -> list[str]:
    """Insert REPLACE_WITH placeholders for bots not yet in app_secrets."""
    defaults = {
        "TELEGRAM_BOT_TOKEN": "REPLACE_WITH_TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID": "REPLACE_WITH_TELEGRAM_CHAT_ID",
        "DINGTALK_WEBHOOK_URL": "REPLACE_WITH_DINGTALK_WEBHOOK",
        "DINGTALK_SECRET": "REPLACE_WITH_DINGTALK_SECRET",
        "FEISHU_WEBHOOK_URL": "REPLACE_WITH_FEISHU_WEBHOOK",
        "FEISHU_APP_ID": "REPLACE_WITH_FEISHU_APP_ID",
        "FEISHU_APP_SECRET": "REPLACE_WITH_FEISHU_APP_SECRET",
        "FEISHU_RECEIVE_ID": "REPLACE_WITH_FEISHU_RECEIVE_ID",
        "FEISHU_API_BASE": "https://open.larksuite.com",
        "POTATO_NOTIFY_ENABLED": "true",
        "POTATO_NOTIFY_CHANNELS": "telegram,dingtalk",
    }
    existing = store.load_all()
    added = []
    for key, value in defaults.items():
        if key not in existing:
            store.upsert(key, value, category="bot")
            added.append(key)
    return added


def upsert_bot_secret(key: str, value: str) -> None:
    from potato.bootstrap_config import load_bootstrap_settings
    from potato.secret_store import SecretStore

    try:
        bootstrap = load_bootstrap_settings()
        if bootstrap.crdb_dsn:
            store = SecretStore(bootstrap)
            store.ensure_schema()
            store.upsert(key, value, category="bot")
        else:
            from potato.vault import Vault
            Vault().store(key, value)
    except Exception as exc:
        logger.warning("upsert_bot_secret failed for %s: %s", key, exc)
