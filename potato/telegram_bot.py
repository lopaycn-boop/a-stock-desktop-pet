"""Telegram bot command handler — polling or webhook, replies to /start."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import httpx

from potato.config import load_settings
from potato.notifications import BotNotifier, is_live_secret, upsert_bot_secret

logger = logging.getLogger("potato.telegram")

# Conflict backoff settings
_CONFLICT_INITIAL_WAIT = 15  # seconds
_CONFLICT_MAX_WAIT = 120  # seconds
_STARTUP_DELAY = 5  # seconds delay before first poll to avoid overlap during deploy


class TelegramRunner:
    """Listen for /start and commands; bind chat_id to app_secrets."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._offset = 0
        self._conflict_count = 0
        self.status: dict[str, Any] = {
            "started": False,
            "mode": None,
            "bot_username": None,
            "last_error": None,
            "messages_handled": 0,
            "last_message_at": None,
        }

    def start(self) -> dict[str, Any]:
        settings = load_settings()
        token = settings.telegram_bot_token
        if not is_live_secret(token):
            self.status["last_error"] = "TELEGRAM_BOT_TOKEN not configured"
            logger.info(
                "Telegram 未启动: token 未配置 (设置环境变量 TELEGRAM_BOT_TOKEN 或调用 /api/bots/telegram/connect)"
            )
            return {"ok": False, "reason": self.status["last_error"]}

        me = BotNotifier(settings).telegram_get_me()
        if me.get("ok"):
            self.status["bot_username"] = me.get("result", {}).get("username")
            logger.info("Telegram bot @%s", self.status["bot_username"])
        else:
            self.status["last_error"] = me.get("description") or me.get("error")
            logger.warning("Telegram getMe failed: %s", self.status["last_error"])
            return {"ok": False, "reason": self.status["last_error"]}

        public = os.getenv("POTATO_PUBLIC_URL", "").strip()
        if public:
            result = BotNotifier(settings).telegram_set_webhook(public)
            logger.info("Telegram webhook mode: %s", result)
            self.status.update({"started": bool(result.get("ok")), "mode": "webhook"})
            return {"ok": bool(result.get("ok")), "mode": "webhook", "bot_username": self.status["bot_username"], **result}

        # Force delete webhook and drop pending updates to avoid conflicts
        self.delete_webhook(drop_pending=True)
        if self._thread and self._thread.is_alive():
            return {
                "ok": True,
                "mode": "polling",
                "already_running": True,
                "bot_username": self.status["bot_username"],
            }

        self._stop.clear()
        self._conflict_count = 0
        self._thread = threading.Thread(target=self._poll_loop, name="telegram-poller", daemon=True)
        self._thread.start()
        self.status.update({"started": True, "mode": "polling"})
        logger.info("Telegram polling started — message @%s and send /start", self.status["bot_username"])
        return {"ok": True, "mode": "polling", "bot_username": self.status["bot_username"]}

    def stop(self) -> None:
        self._stop.set()

    def delete_webhook(self, drop_pending: bool = False) -> dict[str, Any]:
        settings = load_settings()
        token = settings.telegram_bot_token
        if not is_live_secret(token):
            return {"ok": False, "error": "no token"}
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/deleteWebhook",
                json={"drop_pending_updates": drop_pending},
                timeout=30.0,
            )
            result = resp.json()
            logger.info("deleteWebhook(drop_pending=%s): %s", drop_pending, result)
            return result
        except Exception as exc:
            logger.warning("deleteWebhook failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def send_to_chat(self, chat_id: int | str, text: str) -> dict[str, Any]:
        settings = load_settings()
        token = settings.telegram_bot_token
        if not is_live_secret(token):
            return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=30.0,
            )
            data = resp.json()
            if not data.get("ok"):
                return {"ok": False, "error": data.get("description", resp.text)}
            return {"ok": True, "message_id": data.get("result", {}).get("message_id")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def handle_incoming(self, chat_id: int | str, text: str) -> dict[str, Any]:
        upsert_bot_secret("TELEGRAM_CHAT_ID", str(chat_id))
        cmd = (text or "").strip().split()[0].lower() if text else ""

        if cmd in {"/start", "/help"}:
            reply = (
                "\U0001f954 小土豆 A股操盘机器人已连接\n\n"
                "命令：\n"
                "/start — 绑定通知\n"
                "/status — 查看状态\n"
                "/test — 发送测试消息\n\n"
                "每 3 分钟交易循环完成后会自动推送摘要。"
            )
            return self.send_to_chat(chat_id, reply)

        if cmd == "/status":
            st = BotNotifier().channel_status()
            tg = st.get("telegram", {})
            check = "\u2713"
            cross = "\u2717"
            token_mark = check if tg.get("token_set") else cross
            chat_mark = check if tg.get("chat_id_set") else cross
            on_off = "开" if st.get("enabled") else "关"
            reply = (
                "\U0001f954 小土豆状态\n"
                f"Telegram token: {token_mark}\n"
                f"Chat 已绑定: {chat_mark}\n"
                f"通知开关: {on_off}"
            )
            return self.send_to_chat(chat_id, reply)

        if cmd == "/test":
            return self.send_to_chat(chat_id, "\U0001f954 测试消息 OK — 你可以收到交易推送了")

        if text:
            return self.send_to_chat(chat_id, "收到。发送 /help 查看命令。")
        return {"ok": True, "skipped": True}

    def _poll_loop(self) -> None:
        # Startup delay to let old containers shut down during rolling deploys
        logger.info("Telegram poller: waiting %ds before first poll (deploy grace)...", _STARTUP_DELAY)
        time.sleep(_STARTUP_DELAY)

        while not self._stop.is_set():
            try:
                settings = load_settings()
                token = settings.telegram_bot_token
                if not is_live_secret(token):
                    time.sleep(10)
                    continue

                resp = httpx.get(
                    f"https://api.telegram.org/bot{token}/getUpdates",
                    params={"offset": self._offset, "timeout": 20},
                    timeout=35.0,
                )
                data = resp.json()
                if not data.get("ok"):
                    err = data.get("description", str(data))
                    self.status["last_error"] = err

                    # Handle 409 Conflict specifically
                    if resp.status_code == 409 or "Conflict" in err:
                        self._conflict_count += 1
                        wait = min(
                            _CONFLICT_INITIAL_WAIT * (2 ** (self._conflict_count - 1)),
                            _CONFLICT_MAX_WAIT,
                        )
                        logger.warning(
                            "getUpdates 409 Conflict (#%d) — another instance is polling. "
                            "Backing off %ds...",
                            self._conflict_count,
                            wait,
                        )
                        # After 5 consecutive conflicts, try to reclaim by deleting webhook
                        if self._conflict_count % 5 == 0:
                            logger.info("Attempting to reclaim polling via deleteWebhook...")
                            self.delete_webhook(drop_pending=True)
                        time.sleep(wait)
                        continue

                    logger.warning("getUpdates failed: %s", err)
                    time.sleep(5)
                    continue

                # Success — reset conflict counter
                self._conflict_count = 0

                for item in data.get("result") or []:
                    self._offset = max(self._offset, int(item.get("update_id", 0)) + 1)
                    msg = item.get("message") or item.get("edited_message") or {}
                    chat = msg.get("chat") or {}
                    chat_id = chat.get("id")
                    text = msg.get("text") or ""
                    if chat_id is not None:
                        logger.info("Telegram message from %s: %s", chat_id, text[:80])
                        self.status["messages_handled"] += 1
                        self.status["last_message_at"] = time.time()
                        self.status["last_error"] = None
                        result = self.handle_incoming(chat_id, text)
                        if not result.get("ok") and not result.get("skipped"):
                            self.status["last_error"] = result.get("error")
                            logger.warning("Reply failed chat=%s: %s", chat_id, result)
            except Exception as exc:
                self.status["last_error"] = str(exc)
                logger.warning("Telegram poll error: %s", exc)
                time.sleep(5)


_runner = TelegramRunner()


def start_telegram_runner() -> dict[str, Any]:
    return _runner.start()


def stop_telegram_runner() -> None:
    _runner.stop()


def get_telegram_runner() -> TelegramRunner:
    return _runner


def telegram_runner_status() -> dict[str, Any]:
    r = _runner
    alive = bool(r._thread and r._thread.is_alive())
    return {**r.status, "poller_alive": alive}
