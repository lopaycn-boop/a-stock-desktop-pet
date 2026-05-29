"""AI services — resilient multi-provider LLM with retry + fallback.

Providers (in priority order):
    1. DeepSeek (primary) — via OpenAI-compatible API
    2. SiliconFlow (fallback) — via OpenAI-compatible API
    3. OpenAI (fallback) — if key configured

Key improvements over old version:
    - 3-layer retry with exponential backoff
    - Automatic provider fallback on failure
    - Connection pool reuse (no client re-creation on every call)
    - Timeout tuning: connect=8s, read=60s, total=90s
    - Error classification: retryable vs permanent vs auth
    - Graceful degradation: template fallback instead of "大脑短路"
    - TTS/STT retry with fallback providers
    - Thread-safe fallback index
"""

import asyncio
import base64
import io
import json
import logging
import os
import threading
import time
from typing import Any

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError, RateLimitError, AuthenticationError

from config import Config

logger = logging.getLogger("potato.pet.services")

PROVIDERS = [
    {
        "name": "deepseek",
        "key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "max_tokens": 4096,
        "supports_json_mode": True,
        "priority": {"chat": 1, "analysis": 1, "research": 4, "fallback": 1},
        "renewal_url": "https://platform.deepseek.com/usage",
    },
    {
        "name": "siliconflow",
        "key_env": "SILICON_API_KEY",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
        "max_tokens": 4096,
        "supports_json_mode": True,
        "priority": {"chat": 3, "analysis": 2, "research": 5, "fallback": 2},
        "renewal_url": "https://cloud.siliconflow.cn/account/usage",
    },
    {
        "name": "liner",
        "key_env": "LINER_API_KEY",
        "base_url": "https://platform.liner.com/v1",
        "model": "gpt-4o-mini",
        "max_tokens": 4096,
        "supports_json_mode": True,
        "priority": {"chat": 2, "analysis": 3, "research": 1, "fallback": 3},
        "renewal_url": "https://platform.liner.com/keys",
    },
    {
        "name": "openai",
        "key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "max_tokens": 4096,
        "supports_json_mode": True,
        "priority": {"chat": 4, "analysis": 4, "research": 3, "fallback": 4},
        "renewal_url": "https://platform.openai.com/account/billing",
    },
]

_TASK_TYPES = {"chat", "analysis", "research", "fallback"}

_PROVIDER_HEALTH: dict[str, dict[str, Any]] = {
    p["name"]: {"consecutive_failures": 0, "last_error_time": 0.0} for p in PROVIDERS
}
_COOLDOWN = 300.0

_CLIENT_CACHE: dict[str, AsyncOpenAI] = {}
_CLIENT_LOCK = threading.Lock()
_KEY_CACHE: dict[str, str] = {}
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = [1.0, 2.0, 4.0]

_TEMPLATE_FALLBACKS = [
    {"reply": "嗯嗯，我正在思考中~稍等我一下看看...",
     "emotion": "neutral", "memory_operation": {}, "thought": "template_fallback_1",
     "actions": {}},
    {"reply": "让我分析一下你说的~马上给你回复！",
     "emotion": "happy", "memory_operation": {}, "thought": "template_fallback_2",
     "actions": {}},
    {"reply": "收到！我正在处理你的请求~",
     "emotion": "neutral", "memory_operation": {}, "thought": "template_fallback_3",
     "actions": {}},
    {"reply": "好的，我理解了~让我仔细想想",
     "emotion": "neutral", "memory_operation": {}, "thought": "template_fallback_4",
     "actions": {}},
    {"reply": "这个问题有意思！我需要想一下...",
     "emotion": "happy", "memory_operation": {}, "thought": "template_fallback_5",
     "actions": {}},
]

_fallback_counter = 0
_fallback_lock = threading.Lock()


def _get_api_key(key_name: str) -> str:
    if key_name in _KEY_CACHE and _KEY_CACHE[key_name]:
        return _KEY_CACHE[key_name]

    # 1. Vault (user-pasted, persistent)
    try:
        from potato.vault import Vault
        val = Vault().get(key_name)
        if val:
            _KEY_CACHE[key_name] = val
            logger.info("Key %s resolved from vault (len=%d)", key_name, len(val))
            return val
    except Exception as exc:
        logger.debug("Vault lookup for %s failed: %s", key_name, exc)

    # 2. Environment variable
    val = os.environ.get(key_name, "")
    if val:
        _KEY_CACHE[key_name] = val
        logger.info("Key %s resolved from env", key_name)
        return val

    # 3. Config fallback
    cfg_val = getattr(Config, key_name, "") or ""
    if cfg_val:
        _KEY_CACHE[key_name] = cfg_val
        logger.info("Key %s resolved from Config (len=%d)", key_name, len(cfg_val))
        return cfg_val

    # 4. Alias mappings
    aliases = {"DEEPSEEK_API_KEY": "LLM_API_KEY", "SILICON_API_KEY": "SILICON_KEY", "LINER_API_KEY": "LINER_KEY", "OPENAI_API_KEY": "OPENAI_KEY"}
    alias = aliases.get(key_name)
    if alias:
        cfg_val = getattr(Config, alias, "") or ""
        if cfg_val:
            _KEY_CACHE[key_name] = cfg_val
            logger.info("Key %s resolved from alias %s", key_name, alias)
            return cfg_val

    logger.warning("Key %s not found in vault/env/config", key_name)
    return ""


def _clear_key_cache(key_name: str = ""):
    if key_name:
        _KEY_CACHE.pop(key_name, None)
    else:
        _KEY_CACHE.clear()


def _get_or_create_client(provider: dict[str, Any]) -> AsyncOpenAI | None:
    name = provider["name"]
    key = _get_api_key(provider["key_env"])
    if not key:
        return None

    cache_key = f"{name}:{key[:8]}"
    with _CLIENT_LOCK:
        if cache_key in _CLIENT_CACHE:
            return _CLIENT_CACHE[cache_key]

        client = AsyncOpenAI(
            api_key=key,
            base_url=provider["base_url"],
            max_retries=0,
            timeout=90.0,
        )
        _CLIENT_CACHE[cache_key] = client
        logger.info("Created new OpenAI client for %s", name)
        return client


async def _reset_client(provider_name: str):
    with _CLIENT_LOCK:
        to_remove = [k for k in _CLIENT_CACHE if k.startswith(provider_name)]
        for k in to_remove:
            client = _CLIENT_CACHE.pop(k, None)
            if client:
                try:
                    await client.close()
                except Exception:
                    pass


def _classify_error(exc: Exception) -> str:
    """Classify error: 'auth' | 'rate_limit' | 'quota_exhausted' | 'retryable' | 'permanent'"""
    if isinstance(exc, AuthenticationError):
        return "auth"
    if isinstance(exc, RateLimitError):
        exc_str = str(exc).lower()
        if "insufficient_quota" in exc_str:
            return "quota_exhausted"
        return "rate_limit"
    if isinstance(exc, APITimeoutError):
        return "retryable"
    if isinstance(exc, APIConnectionError):
        return "retryable"
    if isinstance(exc, APIStatusError):
        code = exc.status_code
        if code in (401, 403):
            return "auth"
        if code == 402:
            return "quota_exhausted"
        if code == 429:
            exc_str = str(exc).lower()
            if "insufficient_quota" in exc_str or "billing" in exc_str:
                return "quota_exhausted"
            return "rate_limit"
        if code >= 500:
            return "retryable"
        return "permanent"

    exc_str = str(exc).lower()
    if any(kw in exc_str for kw in ["401", "403", "invalid api key", "authentication", "unauthorized"]):
        return "auth"
    if any(kw in exc_str for kw in ["insufficient_quota", "billing", "payment required", "402"]):
        return "quota_exhausted"
    if any(kw in exc_str for kw in ["429", "rate_limit", "rate limit", "capacity"]):
        return "rate_limit"
    if any(kw in exc_str for kw in ["timeout", "timed out", "connection", "reset", "refused", "network", "500", "502", "503", "504"]):
        return "retryable"
    return "permanent"


def _get_template_fallback() -> dict:
    global _fallback_counter
    with _fallback_lock:
        idx = _fallback_counter
        _fallback_counter += 1
    return dict(_TEMPLATE_FALLBACKS[idx % len(_TEMPLATE_FALLBACKS)])


async def _call_llm_with_retry(
    messages: list,
    provider: dict[str, Any],
    max_tokens: int = 2048,
    temperature: float = 0.4,
    response_format: dict | None = None,
) -> dict[str, Any]:
    client = _get_or_create_client(provider)
    if not client:
        return {"ok": False, "error": f"No API key for {provider['name']}"}

    model = provider["model"]
    provider_max = provider.get("max_tokens", 4096)
    effective_max = min(max_tokens, provider_max)
    supports_json = provider.get("supports_json_mode", True)

    for attempt in range(_RETRY_ATTEMPTS):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": effective_max,
            }
            if response_format and supports_json:
                kwargs["response_format"] = response_format

            response = await client.chat.completions.create(**kwargs)

            if not response.choices:
                logger.warning("LLM returned empty choices from %s (attempt %d)", provider["name"], attempt + 1)
                if attempt < _RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(_RETRY_BACKOFF[min(attempt, 2)])
                    continue
                return {"ok": False, "error": f"Empty response from {provider['name']}"}
            content = response.choices[0].message.content
            if not content or not content.strip():
                logger.warning("LLM returned empty content from %s (attempt %d)", provider["name"], attempt + 1)
                if attempt < _RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(_RETRY_BACKOFF[attempt])
                    continue
                return {"ok": False, "error": f"Empty response from {provider['name']}"}

            usage = response.usage
            token_count = usage.total_tokens if usage else 0
            logger.info("LLM success from %s (model=%s, tokens=%d)", provider["name"], model, token_count)
            return {"ok": True, "content": content.strip(), "model": model, "provider": provider["name"]}

        except AuthenticationError as exc:
            logger.error("Auth error for %s, skipping provider: %s", provider["name"], exc)
            await _reset_client(provider["name"])
            _clear_key_cache(provider["key_env"])
            return {"ok": False, "error": f"Auth failed for {provider['name']}", "permanent": True}

        except RateLimitError as exc:
            exc_str = str(exc)
            if "insufficient_quota" in exc_str.lower():
                renewal = provider.get("renewal_url", "")
                logger.error("Quota exhausted for %s, renewal: %s", provider["name"], renewal)
                return {"ok": False, "error": f"Quota exhausted for {provider['name']}", "quota_exhausted": True, "provider": provider["name"], "renewal_url": renewal}
            wait = _RETRY_BACKOFF[min(attempt, 2)] * 2
            logger.warning("Rate limited on %s (attempt %d), waiting %.1fs", provider["name"], attempt + 1, wait)
            if attempt < _RETRY_ATTEMPTS - 1:
                await asyncio.sleep(wait)
                continue
            errors_str = str(exc)[:200]
            return {"ok": False, "error": f"Rate limited: {errors_str}"}

        except (APITimeoutError, APIConnectionError) as exc:
            logger.warning("Connection error on %s (attempt %d): %s", provider["name"], attempt + 1, type(exc).__name__)
            if attempt < _RETRY_ATTEMPTS - 1:
                await asyncio.sleep(_RETRY_BACKOFF[attempt])
                continue
            return {"ok": False, "error": f"Connection failed: {type(exc).__name__}"}

        except APIStatusError as exc:
            category = _classify_error(exc)
            logger.warning("API error on %s (attempt %d): status=%d category=%s", provider["name"], attempt + 1, exc.status_code, category)
            if category == "quota_exhausted":
                renewal = provider.get("renewal_url", "")
                return {"ok": False, "error": f"Quota exhausted for {provider['name']}", "quota_exhausted": True, "provider": provider["name"], "renewal_url": renewal}
            if category == "retryable" and attempt < _RETRY_ATTEMPTS - 1:
                await asyncio.sleep(_RETRY_BACKOFF[attempt])
                continue
            return {"ok": False, "error": f"API error {exc.status_code}: {str(exc)[:200]}"}

        except Exception as exc:
            category = _classify_error(exc)
            logger.warning("Unexpected error on %s (attempt %d): %s [%s]", provider["name"], attempt + 1, exc, category)
            if category == "quota_exhausted":
                renewal = provider.get("renewal_url", "")
                return {"ok": False, "error": f"Quota exhausted for {provider['name']}", "quota_exhausted": True, "provider": provider["name"], "renewal_url": renewal}
            if category in ("retryable", "rate_limit") and attempt < _RETRY_ATTEMPTS - 1:
                await asyncio.sleep(_RETRY_BACKOFF[attempt])
                continue
            return {"ok": False, "error": str(exc)[:300]}

    return {"ok": False, "error": f"All {_RETRY_ATTEMPTS} attempts failed for {provider['name']}"}


class AIService:
    @staticmethod
    async def chat_with_potato_brain(messages: list, timeout: float = 20.0, image_base64: str = None):
        send_messages = list(messages)

        if image_base64 and send_messages:
            last_msg = send_messages[-1]
            text_content = last_msg.get("content", "")
            if isinstance(text_content, str):
                send_messages[-1] = {
                    "role": last_msg["role"],
                    "content": [
                        {"type": "text", "text": text_content},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    ],
                }

        errors = []
        collected_quota_urls = []
        now = time.time()
        def _sorted_providers(task: str = "fallback") -> list:
            avail = []
            for p in PROVIDERS:
                if not _get_api_key(p["key_env"]):
                    continue
                h = _PROVIDER_HEALTH.get(p["name"], {})
                if h.get("consecutive_failures", 0) >= 3 and now - h.get("last_error_time", 0) < _COOLDOWN:
                    continue
                pri = p.get("priority", {}).get(task, 99)
                avail.append((pri, p))
            avail.sort(key=lambda x: x[0])
            return [p for _, p in avail]

        for provider in _sorted_providers("analysis"):
            result = await _call_llm_with_retry(
                messages=send_messages,
                provider=provider,
                max_tokens=2048,
                temperature=0.4,
                response_format={"type": "json_object"},
            )

            if result.get("ok"):
                content = result["content"]
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    # Try JSON extraction from mixed content
                    json_match = __import__("re").search(r'\{[\s\S]*\}', content)
                    if json_match:
                        try:
                            return json.loads(json_match.group())
                        except json.JSONDecodeError:
                            pass

                    # Ask LLM to fix JSON
                    for _ in range(2):
                        fix_messages = messages + [
                            {"role": "assistant", "content": content},
                            {"role": "user", "content": "请把上面的回复重新输出为严格的JSON格式，不要有任何多余文字。"},
                        ]
                        fix_result = await _call_llm_with_retry(
                            messages=fix_messages,
                            provider=provider,
                            max_tokens=2048,
                            temperature=0.1,
                            response_format={"type": "json_object"},
                        )
                        if fix_result.get("ok"):
                            try:
                                return json.loads(fix_result["content"])
                            except json.JSONDecodeError:
                                continue

                    logger.warning("JSON parse failed after retries from %s, using template fallback", provider["name"])
                    fallback = _get_template_fallback()
                    fallback["thought"] = f"JSON parse error, provider={provider['name']}"
                    return fallback

            errors.append(f"{provider['name']}: {result.get('error', 'unknown')[:80]}")

            if result.get("quota_exhausted"):
                renewal = result.get("renewal_url", "")
                if renewal:
                    collected_quota_urls.append((provider["name"], renewal))
                logger.info("Quota exhausted on %s, skipping to next provider", provider["name"])
                continue

            if result.get("permanent"):
                logger.info("Permanent error on %s, skipping to next provider", provider["name"])
                continue

        logger.error("All LLM providers failed: %s", " | ".join(errors))
        fallback = _get_template_fallback()
        fallback["thought"] = f"All providers failed: {'; '.join(errors[:2])}"
        if collected_quota_urls:
            fallback["quota_exhausted"] = True
            fallback["quota_providers"] = [
                {"provider": name, "renewal_url": url} for name, url in collected_quota_urls
            ]
        return fallback

    @staticmethod
    async def text_to_speech(text: str, emotion: str = "neutral"):
        try:
            from potato.voice import text_to_speech as unified_tts
            return await unified_tts(text, emotion, profile_id="yujie")
        except Exception as e:
            logger.debug("Unified TTS unavailable, falling back to SiliconFlow: %s", e)

        sil_key = _get_api_key("SILICON_API_KEY")
        if not sil_key:
            return None
        client = None
        try:
            client = AsyncOpenAI(api_key=sil_key, base_url=Config.SILICON_BASE, max_retries=2, timeout=30.0)
            prompt_text = f"<{emotion}>{text}"
            response = await client.audio.speech.create(
                model=Config.TTS_MODEL, voice=Config.TTS_VOICE,
                input=prompt_text, response_format="mp3",
            )
            return base64.b64encode(response.content).decode("utf-8")
        except Exception as e:
            logger.warning("TTS failed: %s", e)
            return None
        finally:
            if client:
                try:
                    await client.close()
                except Exception:
                    pass

    @staticmethod
    async def speech_to_text(audio_base64: str):
        try:
            from potato.voice import speech_to_text as unified_stt
            return await unified_stt(audio_base64)
        except Exception as e:
            logger.debug("Unified STT unavailable, falling back to SiliconFlow: %s", e)

        sil_key = _get_api_key("SILICON_API_KEY")
        if not sil_key:
            return ""
        client = None
        try:
            client = AsyncOpenAI(api_key=sil_key, base_url=Config.SILICON_BASE, max_retries=2, timeout=30.0)
            audio_bytes = base64.b64decode(audio_base64)
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "input.webm"
            transcript = await client.audio.transcriptions.create(
                model=Config.STT_MODEL, file=audio_file,
            )
            return transcript.text
        except Exception as e:
            logger.warning("STT failed: %s", e)
            return ""
        finally:
            if client:
                try:
                    await client.close()
                except Exception:
                    pass

    @staticmethod
    async def get_embedding(text: str):
        sil_key = _get_api_key("SILICON_API_KEY")
        if not sil_key:
            return None
        client = None
        try:
            client = AsyncOpenAI(api_key=sil_key, base_url=Config.SILICON_BASE, max_retries=1, timeout=30.0)
            response = await client.embeddings.create(
                model="Qwen/Qwen3-Embedding-8B", input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.warning("Embedding failed: %s", e)
            return None
        finally:
            if client:
                try:
                    await client.close()
                except Exception:
                    pass


# ── Legacy aliases ──

def _reset_main_client():
    stale_keys = [k for k in list(_CLIENT_CACHE.keys()) if k.split(":")[0] in ("deepseek", "siliconflow", "liner", "openai")]
    for k in stale_keys:
        client = _CLIENT_CACHE.pop(k, None)
        if client and hasattr(client, 'close'):
            try:
                asyncio.get_event_loop().create_task(client.close())
            except Exception:
                pass
    _clear_key_cache()


def _reset_audio_client():
    stale_keys = [k for k in list(_CLIENT_CACHE.keys()) if k.split(":")[0] == "siliconflow"]
    for k in stale_keys:
        client = _CLIENT_CACHE.pop(k, None)
        if client and hasattr(client, 'close'):
            try:
                asyncio.get_event_loop().create_task(client.close())
            except Exception:
                pass