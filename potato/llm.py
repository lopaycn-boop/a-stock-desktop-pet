"""Intelligent LLM routing — task-aware provider selection.

Instead of a dumb fallback chain, routes requests to the best provider
based on task type:

    Task Types:
        chat     — Quick conversation, emotion, small talk → DeepSeek (fast/cheap)
        analysis — Structured JSON analysis, trading picks → DeepSeek (best JSON)
        research — News scan, macro context, web search   → Liner (search+citations)
        fallback — Any task when primary fails             → Next available provider

Provider capabilities:
        deepseek   — Fast, cheap, excellent JSON mode, strong Chinese
        siliconflow — DeepSeek-V3 proxy, good JSON, domestic CDN
        liner      — Web search + citations, research-grade, OpenAI-compatible
        openai     — Premium fallback, reliable, expensive

The router checks which providers have keys, which are healthy (not in cooldown),
and routes to the best match for each task.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from potato.config import Settings, load_settings
from potato.security import mask_secret

logger = logging.getLogger("potato.llm")

# ── Provider definitions with capability tags ──────────────────────────

PROVIDERS = [
    {
        "name": "deepseek",
        "url": "https://api.deepseek.com/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
        "supports_json_mode": True,
        "capabilities": ["chat", "analysis", "fallback"],
        "priority": {"chat": 1, "analysis": 1, "research": 4, "fallback": 1},
        "renewal_url": "https://platform.deepseek.com/usage",
    },
    {
        "name": "siliconflow",
        "url": "https://api.siliconflow.cn/v1/chat/completions",
        "key_env": "SILICON_API_KEY",
        "model": "deepseek-ai/DeepSeek-V3",
        "supports_json_mode": True,
        "capabilities": ["analysis", "fallback"],
        "priority": {"chat": 3, "analysis": 2, "research": 5, "fallback": 2},
        "renewal_url": "https://cloud.siliconflow.cn/account/usage",
    },
    {
        "name": "liner",
        "url": "https://platform.liner.com/v1/chat/completions",
        "key_env": "LINER_API_KEY",
        "model": "gpt-4o-mini",
        "supports_json_mode": True,
        "capabilities": ["research", "chat", "analysis", "fallback"],
        "priority": {"chat": 2, "analysis": 3, "research": 1, "fallback": 3},
        "renewal_url": "https://platform.liner.com/keys",
    },
    {
        "name": "openai",
        "url": "https://api.openai.com/v1/chat/completions",
        "key_env": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
        "supports_json_mode": True,
        "capabilities": ["chat", "analysis", "fallback"],
        "priority": {"chat": 4, "analysis": 4, "research": 3, "fallback": 4},
        "renewal_url": "https://platform.openai.com/account/billing",
    },
]

TASK_TYPES = {"chat", "analysis", "research", "fallback"}

# ── Health tracking ────────────────────────────────────────────────────

_provider_health: dict[str, dict[str, Any]] = {
    p["name"]: {"last_error_time": 0.0, "consecutive_failures": 0, "last_success_time": 0.0}
    for p in PROVIDERS
}
_COOLDOWN_SECONDS = 300  # 5 min cooldown after auth errors
_MAX_CONSECUTIVE = 3

# ── Retry config ───────────────────────────────────────────────────────

_MAX_RETRIES = 3
_BACKOFF = [1.0, 2.0, 4.0]
_TIMEOUT = httpx.Timeout(connect=8.0, read=60.0, write=10.0, pool=30.0)


# ── Key resolution ─────────────────────────────────────────────────────

def _model_id(settings: Settings) -> str:
    raw = (settings.llm_model or "deepseek/deepseek-chat").strip()
    if "/" in raw:
        return raw.split("/", 1)[1]
    return raw or "deepseek-chat"


def _get_key(settings: Settings, key_env: str) -> str:
    key = ""
    if key_env == "DEEPSEEK_API_KEY":
        key = settings.deepseek_api_key or ""
    elif key_env == "SILICON_API_KEY":
        import os
        key = os.environ.get("SILICON_API_KEY", "") or os.environ.get("SILICON_KEY", "")
    elif key_env == "LINER_API_KEY":
        import os
        key = os.environ.get("LINER_API_KEY", "")
    elif key_env == "OPENAI_API_KEY":
        import os
        key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        try:
            from potato.vault import Vault
            key = Vault().get(key_env) or ""
        except Exception:
            pass
    if not key:
        import os
        key = os.environ.get(key_env, "")
    return key.strip()


def _classify_status(status_code: int, error_body: str = "") -> str:
    if status_code in (401, 403):
        return "auth"
    if status_code == 402:
        return "quota_exhausted"
    if status_code == 429:
        return "rate_limit"
    if status_code >= 500:
        return "retryable"
    if "insufficient_quota" in error_body or "billing" in error_body.lower():
        return "quota_exhausted"
    return "permanent"


# ── Provider selection ─────────────────────────────────────────────────

def _available_providers(settings: Settings, task: str = "fallback") -> list[dict]:
    """Return providers sorted by priority for the given task, excluding those in cooldown."""
    candidates = []
    now = time.time()
    for p in PROVIDERS:
        key = _get_key(settings, p["key_env"])
        if not key:
            continue
        health = _provider_health[p["name"]]
        if health["consecutive_failures"] >= _MAX_CONSECUTIVE:
            if now - health["last_error_time"] < _COOLDOWN_SECONDS:
                logger.debug("Provider %s in cooldown (%d failures, %.0fs ago)",
                             p["name"], health["consecutive_failures"],
                             now - health["last_error_time"])
                continue
            else:
                health["consecutive_failures"] = 0
        pri = p.get("priority", {}).get(task, 99)
        candidates.append((pri, p))
    candidates.sort(key=lambda x: x[0])
    return [p for _, p in candidates]


def _mark_success(provider_name: str) -> None:
    h = _provider_health.get(provider_name)
    if h:
        h["consecutive_failures"] = 0
        h["last_success_time"] = time.time()


def _mark_failure(provider_name: str, error_type: str) -> None:
    h = _provider_health.get(provider_name)
    if h:
        h["consecutive_failures"] = h.get("consecutive_failures", 0) + 1
        h["last_error_time"] = time.time()
        if error_type == "auth":
            h["consecutive_failures"] = _MAX_CONSECUTIVE


# ── Core chat function ─────────────────────────────────────────────────

def chat(
    user_prompt: str,
    *,
    system: str = "你是保守型A股操盘分析师，用简洁中文输出。",
    settings: Settings | None = None,
    max_tokens: int = 1200,
    task: str = "fallback",
    use_json: bool = True,
) -> dict[str, Any]:
    """Call LLM with task-aware routing.

    Args:
        task: One of 'chat' (quick reply), 'analysis' (JSON structured),
              'research' (news/web search), or 'fallback' (any available).
        use_json: Whether to request JSON response format.
    """
    if task not in TASK_TYPES:
        logger.warning("Unknown task type '%s', falling back to 'fallback'", task)
        task = "fallback"

    settings = settings or load_settings()
    errors = []
    providers = _available_providers(settings, task)

    if not providers:
        logger.warning("No available providers for task '%s', trying all with keys", task)
        for p in PROVIDERS:
            if _get_key(settings, p["key_env"]):
                providers.append(p)
        if not providers:
            return {"ok": False, "error": "没有可用的大模型，请配置API Key", "provider_errors": []}

    for provider in providers:
        key = _get_key(settings, provider["key_env"])
        if not key:
            continue

        model = provider["model"] if provider["name"] != "deepseek" else _model_id(settings)
        supports_json = provider.get("supports_json_mode", True) and use_json

        for attempt in range(_MAX_RETRIES):
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                }
                if supports_json:
                    payload["response_format"] = {"type": "json_object"}

                # Research tasks get higher max_tokens on Liner
                if task == "research" and provider["name"] == "liner":
                    payload["max_tokens"] = max(max_tokens, 2000)

                resp = httpx.post(
                    provider["url"],
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=_TIMEOUT,
                )
                data = resp.json()

                # Handle status codes
                if resp.status_code == 429:
                    error_body = str(data.get("error", {}))
                    if "insufficient_quota" in error_body or "billing" in error_body.lower():
                        _mark_failure(provider["name"], "quota_exhausted")
                        renewal_url = provider.get("renewal_url", "")
                        errors.append(f"{provider['name']}: quota exhausted, renewal: {renewal_url}")
                        break
                    wait = _BACKOFF[min(attempt, 2)] * 2
                    logger.warning("Rate limited on %s, retrying in %.1fs", provider["name"], wait)
                    time.sleep(wait)
                    continue

                if resp.status_code == 402:
                    _mark_failure(provider["name"], "quota_exhausted")
                    renewal_url = provider.get("renewal_url", "")
                    errors.append(f"{provider['name']}: payment required, renewal: {renewal_url}")
                    break

                if resp.status_code in (401, 403):
                    logger.error("Auth error on %s, skipping provider", provider["name"])
                    _mark_failure(provider["name"], "auth")
                    errors.append(f"{provider['name']}: auth error (status={resp.status_code})")
                    break

                if resp.status_code >= 500:
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_BACKOFF[attempt])
                        continue
                    _mark_failure(provider["name"], "server")
                    errors.append(f"{provider['name']}: server error {resp.status_code}")
                    break

                if resp.status_code != 200:
                    err_msg = data.get("error", {})
                    safe_msg = mask_secret(str(err_msg)[:200])
                    errors.append(f"{provider['name']}: HTTP {resp.status_code} {safe_msg}")
                    break

                # Success path
                choices = data.get("choices") or []
                if not choices:
                    logger.warning("Empty choices from %s (attempt %d)", provider["name"], attempt + 1)
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_BACKOFF[attempt])
                        continue
                    errors.append(f"{provider['name']}: empty choices")
                    break

                content = (choices[0].get("message") or {}).get("content") or ""
                if not content.strip():
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_BACKOFF[attempt])
                        continue
                    errors.append(f"{provider['name']}: empty response")
                    break

                _mark_success(provider["name"])
                logger.info("LLM chat success from %s (model=%s, task=%s)", provider["name"], model, task)
                return {
                    "ok": True,
                    "content": content.strip(),
                    "model": model,
                    "provider": provider["name"],
                    "task": task,
                }

            except httpx.TimeoutException as exc:
                logger.warning("Timeout on %s attempt %d: %s", provider["name"], attempt + 1, type(exc).__name__)
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF[attempt])
                    continue
                _mark_failure(provider["name"], "timeout")
                errors.append(f"{provider['name']}: timeout ({type(exc).__name__})")

            except httpx.ConnectError as exc:
                logger.warning("Connect error on %s: %s", provider["name"], exc)
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF[attempt])
                    continue
                _mark_failure(provider["name"], "connect")
                errors.append(f"{provider['name']}: connection failed")

            except json.JSONDecodeError as exc:
                logger.warning("JSON decode error from %s: %s", provider["name"], exc)
                errors.append(f"{provider['name']}: invalid JSON response")
                break

            except Exception as exc:
                logger.warning("Unexpected error on %s: %s", provider["name"], mask_secret(str(exc)))
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF[attempt])
                    continue
                _mark_failure(provider["name"], "unknown")
                errors.append(f"{provider['name']}: {mask_secret(str(exc))[:100]}")

    logger.error("All LLM providers failed for task '%s': %s", task, " | ".join(errors[:3]))
    quota_providers = []
    for err in errors:
        for p in PROVIDERS:
            if p["name"] in err and ("quota" in err.lower() or "payment" in err.lower() or "402" in err):
                from potato.vault import KNOWN_KEYS as _VK
                key_meta = _VK.get(p.get("key_env", ""), {})
                quota_providers.append({
                    "provider": p["name"],
                    "key_env": p.get("key_env", ""),
                    "key_desc": key_meta.get("desc", p["name"]),
                    "renewal_url": p.get("renewal_url", key_meta.get("renewal_url", "")),
                    "dashboard_url": key_meta.get("dashboard_url", p.get("renewal_url", "")),
                })
                break
    result = {"ok": False, "error": "所有大模型暂时不可用，请稍后重试", "provider_errors": errors}
    if quota_providers:
        result["quota_exhausted"] = True
        result["quota_providers"] = quota_providers
        result["error"] = f"你的 {'、'.join(q['key_desc'] for q in quota_providers)} 额度已用完，需要续费才能继续~"
    return result


# ── Convenience wrappers ───────────────────────────────────────────────

def research(prompt: str, *, system: str = "", settings: Settings | None = None, max_tokens: int = 2000) -> dict[str, Any]:
    """Research task — prioritizes providers with web search capability (Liner)."""
    return chat(prompt, system=system or "你是专业金融研究员，提供有来源依据的深度分析。用中文输出，引用数据要标注来源。", settings=settings, max_tokens=max_tokens, task="research", use_json=False)


def analyze(prompt: str, *, system: str = "", settings: Settings | None = None, max_tokens: int = 1500) -> dict[str, Any]:
    """Analysis task — prioritizes structured JSON output capability."""
    return chat(prompt, system=system or "你是保守型A股操盘分析师，用简洁中文输出结构化JSON。", settings=settings, max_tokens=max_tokens, task="analysis", use_json=True)


def quick_chat(prompt: str, *, system: str = "", settings: Settings | None = None, max_tokens: int = 800) -> dict[str, Any]:
    """Quick chat task — prioritizes speed and cost efficiency."""
    return chat(prompt, system=system or "你是小土豆，一个可爱的AI操盘桌宠。用简短中文回复。", settings=settings, max_tokens=max_tokens, task="chat", use_json=False)


# ── Legacy alias ───────────────────────────────────────────────────────

call_llm = chat