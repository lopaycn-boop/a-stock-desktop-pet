"""Security utilities — secret masking, audit logging, and input validation.

Central place for all security-related helpers used across the potato module.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("potato.security")

# Patterns that should never appear in logs or API responses
SENSITIVE_PATTERNS = [
    (re.compile(r"(api[_-]?key\s*[=:]\s*)[^\s,}\"']+", re.IGNORECASE), r"\1***MASKED***"),
    (re.compile(r"(password\s*[=:]\s*)[^\s,}\"']+", re.IGNORECASE), r"\1***MASKED***"),
    (re.compile(r"(token\s*[=:]\s*)[^\s,}\"']+", re.IGNORECASE), r"\1***MASKED***"),
    (re.compile(r"(secret\s*[=:]\s*)[^\s,}\"']+", re.IGNORECASE), r"\1***MASKED***"),
    (re.compile(r"(Bearer\s+)[^\s]+", re.IGNORECASE), r"\1***MASKED***"),
    (re.compile(r"(sk-)[a-zA-Z0-9]{8,}", re.IGNORECASE), r"\1***MASKED***"),
    (re.compile(r"(Authorization.*?:\s*Bearer\s+)[^\s,}\"']+", re.IGNORECASE), r"\1***MASKED***"),
    (re.compile(r"(account.*?[=:]\s*)[\d@.a-zA-Z]{4,}", re.IGNORECASE), r"\1***MASKED***"),
]


def mask_secret(value: str, visible_prefix: int = 4, visible_suffix: int = 4) -> str:
    """Mask a secret value, showing only first/last few chars.

    >>> mask_secret("sk-abc123def456 ghi789")
    'sk-a***789'
    >>> mask_secret("short")
    '***'
    """
    if not value:
        return ""
    if len(value) <= visible_prefix + visible_suffix + 3:
        return "***"
    return f"{value[:visible_prefix]}***{value[-visible_suffix:]}"


def sanitize_dict(data: dict[str, Any], sensitive_keys: set[str] | None = None) -> dict[str, Any]:
    """Return a copy of dict with sensitive values masked.

    Default sensitive keys include common credential field names.
    """
    if sensitive_keys is None:
        sensitive_keys = {
            "password", "passwd", "pwd", "secret", "token", "api_key", "apikey",
            "key", "credential", "auth", "authorization", "cookie", "session",
            "deepseek_api_key", "silicon_api_key", "telegram_bot_token",
            "feishu_app_secret", "dingtalk_secret", "feishu_app_id",
        }

    result = {}
    for k, v in data.items():
        key_lower = k.lower()
        if key_lower in sensitive_keys or any(s in key_lower for s in ("password", "secret", "token", "key", "credential")):
            if isinstance(v, str):
                result[k] = mask_secret(v)
            else:
                result[k] = "***MASKED***"
        elif isinstance(v, dict):
            result[k] = sanitize_dict(v, sensitive_keys)
        else:
            result[k] = v
    return result


def sanitize_log_message(msg: str) -> str:
    """Remove potential secrets from log messages using regex patterns."""
    for pattern, replacement in SENSITIVE_PATTERNS:
        msg = pattern.sub(replacement, msg)
    return msg


class SecretSafeLogger:
    """Wrapper that auto-masks secrets before logging."""

    def __init__(self, logger_instance: logging.Logger):
        self._logger = logger_instance

    def _safe_args(self, *args: Any) -> tuple:
        return tuple(
            sanitize_log_message(str(a)) if isinstance(a, str) else a
            for a in args
        )

    def _safe_kwargs(self, **kwargs: Any) -> dict[str, Any]:
        safe = {}
        for k, v in kwargs.items():
            if isinstance(v, str):
                safe[k] = sanitize_log_message(v)
            elif isinstance(v, dict):
                safe[k] = sanitize_dict(v)
            else:
                safe[k] = v
        return safe

    def info(self, msg: str, *args: Any, **kwargs: Any):
        self._logger.info(sanitize_log_message(msg), *self._safe_args(*args), **self._safe_kwargs(**kwargs))

    def warning(self, msg: str, *args: Any, **kwargs: Any):
        self._logger.warning(sanitize_log_message(msg), *self._safe_args(*args), **self._safe_kwargs(**kwargs))

    def error(self, msg: str, *args: Any, **kwargs: Any):
        self._logger.error(sanitize_log_message(msg), *self._safe_args(*args), **self._safe_kwargs(**kwargs))

    def debug(self, msg: str, *args: Any, **kwargs: Any):
        self._logger.debug(sanitize_log_message(msg), *self._safe_args(*args), **self._safe_kwargs(**kwargs))

    def exception(self, msg: str, *args: Any, **kwargs: Any):
        self._logger.exception(sanitize_log_message(msg), *self._safe_args(*args), **self._safe_kwargs(**kwargs))


def safe_logger(name: str) -> SecretSafeLogger:
    """Create a secret-safe logger for the given module name."""
    return SecretSafeLogger(logging.getLogger(name))