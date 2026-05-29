"""Bytebot desktop agent client — bridges the pet brain to Bytebot's REST API.

Bytebot runs as a Docker service with its own Linux desktop (XFCE).
This client lets the pet create tasks, monitor progress, and send
direct computer-use commands (screenshot, click, type, etc.).

Ports:
  - 9990: bytebotd (desktop daemon — computer-use API)
  - 9991: bytebot-agent (AI agent — task creation & management)
"""

import asyncio
import base64
import json
import logging
import os
from typing import Any, Optional
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger("potato.pet.bytebot")

_DEFAULT_AGENT_URL = "http://localhost:9991"  # Default; override via BYTEBOT_AGENT_URL env var
_DEFAULT_DESKTOP_URL = "http://localhost:9990"  # Default; override via BYTEBOT_DESKTOP_URL env var
_BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal", "metadata.internal"}


def _validate_url(url_str: str) -> str:
    """Validate a Bytebot URL to prevent SSRF."""
    parsed = urlparse(url_str)
    hostname = parsed.hostname or ""
    if hostname.lower() in _BLOCKED_HOSTS:
        raise ValueError(f"Blocked host: {hostname}")
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid scheme: {parsed.scheme}")
    return url_str.rstrip("/")


def _get_bytebot_urls():
    try:
        from potato.vault import Vault
        v = Vault()
        agent = v.get("BYTEBOT_AGENT_URL") or os.getenv("BYTEBOT_AGENT_URL", _DEFAULT_AGENT_URL)
        desktop = v.get("BYTEBOT_DESKTOP_URL") or os.getenv("BYTEBOT_DESKTOP_URL", _DEFAULT_DESKTOP_URL)
    except Exception:
        agent = os.getenv("BYTEBOT_AGENT_URL", _DEFAULT_AGENT_URL)
        desktop = os.getenv("BYTEBOT_DESKTOP_URL", _DEFAULT_DESKTOP_URL)
    try:
        agent = _validate_url(agent)
        desktop = _validate_url(desktop)
    except ValueError as e:
        logger.error("Bytebot URL validation failed: %s", e)
        agent = _DEFAULT_AGENT_URL
        desktop = _DEFAULT_DESKTOP_URL
    return agent, desktop


def _get_llm_key():
    try:
        from services import _get_api_key
        return _get_api_key("DEEPSEEK_API_KEY")
    except Exception:
        return os.getenv("DEEPSEEK_API_KEY", "")


class BytebotClient:
    """Async client for Bytebot agent + desktop daemon."""

    def __init__(self, agent_url=None, desktop_url=None):
        self.agent_url = agent_url
        self.desktop_url = desktop_url
        self._session: Optional[aiohttp.ClientSession] = None

    def _ensure_urls(self):
        if not self.agent_url or not self.desktop_url:
            self.agent_url, self.desktop_url = _get_bytebot_urls()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=3, sock_read=15)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def is_available(self) -> bool:
        self._ensure_urls()
        try:
            session = await self._get_session()
            async with session.get(f"{self.agent_url}/tasks", params={"limit": 1}) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def is_desktop_available(self) -> bool:
        self._ensure_urls()
        try:
            session = await self._get_session()
            async with session.get(f"{self.desktop_url}/health") as resp:
                return resp.status == 200
        except Exception:
            return False

    async def create_task(self, description: str, files: list = None,
                          priority: str = "MEDIUM", model: dict = None) -> dict:
        """Create a new Bytebot task. Returns the full Task object."""
        self._ensure_urls()
        session = await self._get_session()
        data = {"description": description, "priority": priority}
        if model:
            data["model"] = model

        if files:
            form = aiohttp.FormData()
            form.add_field("description", description)
            form.add_field("priority", priority)
            if model:
                form.add_field("model", json.dumps(model))
            for f in files:
                form.add_field("files", f["data"],
                               filename=f.get("name", "file"),
                               content_type=f.get("type", "application/octet-stream"))
            async with session.post(f"{self.agent_url}/tasks", data=form) as resp:
                return await resp.json()
        else:
            async with session.post(f"{self.agent_url}/tasks", json=data) as resp:
                return await resp.json()

    async def get_task(self, task_id: str) -> Optional[dict]:
        self._ensure_urls()
        session = await self._get_session()
        async with session.get(f"{self.agent_url}/tasks/{task_id}") as resp:
            if resp.status == 200:
                return await resp.json()
            return None

    async def get_task_messages(self, task_id: str, limit: int = 50) -> list:
        self._ensure_urls()
        session = await self._get_session()
        async with session.get(f"{self.agent_url}/tasks/{task_id}/messages",
                               params={"limit": limit}) as resp:
            if resp.status == 200:
                return await resp.json()
            return []

    async def add_message(self, task_id: str, message: str) -> Optional[dict]:
        self._ensure_urls()
        session = await self._get_session()
        async with session.post(f"{self.agent_url}/tasks/{task_id}/messages",
                                json={"message": message}) as resp:
            if resp.status == 201:
                return await resp.json()
            return None

    async def cancel_task(self, task_id: str) -> Optional[dict]:
        self._ensure_urls()
        session = await self._get_session()
        async with session.post(f"{self.agent_url}/tasks/{task_id}/cancel") as resp:
            if resp.status == 200:
                return await resp.json()
            return None

    async def takeover_task(self, task_id: str) -> Optional[dict]:
        self._ensure_urls()
        session = await self._get_session()
        async with session.post(f"{self.agent_url}/tasks/{task_id}/takeover") as resp:
            if resp.status == 200:
                return await resp.json()
            return None

    async def resume_task(self, task_id: str) -> Optional[dict]:
        self._ensure_urls()
        session = await self._get_session()
        async with session.post(f"{self.agent_url}/tasks/{task_id}/resume") as resp:
            if resp.status == 200:
                return await resp.json()
            return None

    async def list_models(self) -> list:
        self._ensure_urls()
        session = await self._get_session()
        async with session.get(f"{self.agent_url}/tasks/models") as resp:
            if resp.status == 200:
                return await resp.json()
            return []

    async def computer_use(self, action: str, **params) -> dict:
        """Send a direct computer-use command to bytebotd (port 9990).

        Actions: screenshot, click_mouse, type_text, move_mouse, scroll,
                 press_keys, type_keys, paste_text, wait, cursor_position,
                 application, write_file, read_file, drag_mouse, trace_mouse,
                 press_mouse.
        """
        self._ensure_urls()
        session = await self._get_session()
        payload = {"action": action, **params}
        async with session.post(f"{self.desktop_url}/computer-use", json=payload) as resp:
            if resp.status == 200:
                ct = resp.headers.get("Content-Type", "")
                if "json" in ct:
                    return await resp.json()
                return {"ok": True, "action": action}
            try:
                err = await resp.json()
                return {"ok": False, "error": err.get("message", str(resp.status))}
            except Exception:
                return {"ok": False, "error": f"HTTP {resp.status}"}

    async def screenshot(self) -> dict:
        return await self.computer_use("screenshot")

    async def click(self, x: int, y: int, button: str = "left", click_count: int = 1):
        return await self.computer_use("click_mouse",
                                        coordinates={"x": x, "y": y},
                                        button=button, clickCount=click_count)

    async def type_text(self, text: str, delay: int = None):
        params = {"text": text}
        if delay is not None:
            params["delay"] = delay
        return await self.computer_use("type_text", **params)

    async def press_keys(self, keys: list):
        return await self.computer_use("press_keys", keys=keys, press="down")

    async def scroll(self, direction: str, count: int = 3, x: int = None, y: int = None):
        params = {"direction": direction, "scrollCount": count}
        if x is not None and y is not None:
            params["coordinates"] = {"x": x, "y": y}
        return await self.computer_use("scroll", **params)

    async def open_app(self, app: str):
        return await self.computer_use("application", application=app)

    async def read_file(self, path: str) -> dict:
        return await self.computer_use("read_file", path=path)

    async def write_file(self, path: str, data: str) -> dict:
        return await self.computer_use("write_file", path=path, data=data)

    async def wait(self, duration_ms: int):
        return await self.computer_use("wait", duration=duration_ms)

    async def cursor_position(self) -> dict:
        return await self.computer_use("cursor_position")


_bytebot_client: Optional[BytebotClient] = None


def get_bytebot_client() -> BytebotClient:
    global _bytebot_client
    if _bytebot_client is None:
        _bytebot_client = BytebotClient()
    return _bytebot_client


async def poll_task_until_done(task_id: str, send_func,
                                interval: float = 1.0, max_wait: float = 300.0):
    """Poll a Bytebot task and send status updates to the frontend."""
    client = get_bytebot_client()
    elapsed = 0.0
    last_status = None

    while elapsed < max_wait:
        await asyncio.sleep(interval)
        elapsed += interval

        task = await client.get_task(task_id)
        if not task:
            await send_func("bytebot_task_update", {
                "task_id": task_id, "status": "error", "error": "Task not found"
            })
            return task

        status = task.get("status", "UNKNOWN")
        error = task.get("error")

        if status != last_status:
            last_status = status
            status_cn = {
                "PENDING": "等待中", "RUNNING": "执行中", "NEEDS_HELP": "需要协助",
                "NEEDS_REVIEW": "等待确认", "COMPLETED": "已完成",
                "CANCELLED": "已取消", "FAILED": "失败",
            }.get(status, status)
            await send_func("bytebot_task_update", {
                "task_id": task_id, "status": status, "status_cn": status_cn,
                "error": error, "elapsed": round(elapsed, 1),
            })

        if status in ("COMPLETED", "CANCELLED", "FAILED"):
            result = task.get("result")
            await send_func("bytebot_task_done", {
                "task_id": task_id, "status": status, "result": result,
                "error": error, "elapsed": round(elapsed, 1),
            })
            return task

    await send_func("bytebot_task_update", {
        "task_id": task_id, "status": "TIMEOUT",
        "status_cn": "超时", "error": f"Task did not complete within {max_wait}s",
    })
    return None