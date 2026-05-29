"""Secrets store — unified credential management for CockroachDB and SQLite.

Security: All secrets are Fernet(AES-128-CBC+HMAC-SHA256) encrypted at rest.
  - CockroachDB: values encrypted before storage, decrypted on read
  - SQLite fallback: uses vault table which now stores encrypted values
  - Machine-specific key derivation ensures secrets aren't portable across installs
  - Falls back to base64 if cryptography package is unavailable (NOT secure for production)
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from potato.bootstrap_config import BootstrapSettings, load_bootstrap_settings

try:
    import psycopg2 as _psycopg2
    import psycopg2.extras as _psycopg2_extras
    _HAS_PSYCOPG2 = True
except ImportError:
    _psycopg2 = None
    _psycopg2_extras = None
    _HAS_PSYCOPG2 = False

from potato.vault import _encrypt, _decrypt

SECRET_KEYS = (
    "CRDB_DATABASE_URL",
    "CRDB_CLUSTER_ID",
    "CRDB_SSL_ROOT_CERT",
    "GITHUB_TOKEN",
    "DEEPSEEK_API_KEY",
    "ZEABUR_API_KEY",
    "ZEABUR_PROJECT_ID",
    "ZEABUR_SERVICE_ID",
    "ZEABUR_ENVIRONMENT_ID",
    "GITHUB_REPO",
    "POTATO_API_KEY",
    "POTATO_LLM_MODEL",
    "POTATO_TRADING_MODE",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "DINGTALK_WEBHOOK_URL",
    "DINGTALK_SECRET",
    "FEISHU_WEBHOOK_URL",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_RECEIVE_ID",
    "FEISHU_API_BASE",
    "POTATO_NOTIFY_ENABLED",
    "POTATO_NOTIFY_CHANNELS",
    "POTATO_MAX_SINGLE_CNY",
    "POTATO_MAX_DAILY_CNY",
    "POTATO_DEFAULT_ORDER_SIZE_CNY",
)

# Only these may come from process environment at runtime (bootstrap to reach DB).
BOOTSTRAP_ENV_KEYS = (
    "CRDB_DATABASE_URL",
    "CRDB_CLUSTER_ID",
    "CRDB_SSL_ROOT_CERT",
)


class SecretStore:
    """Read/write unified credentials in CockroachDB app_secrets table.

    All values are Fernet(AES-128-CBC+HMAC-SHA256) encrypted before storage and decrypted on read.
    """

    def __init__(self, bootstrap: BootstrapSettings | None = None):
        self.bootstrap = bootstrap or load_bootstrap_settings()
        if not self.bootstrap.crdb_dsn:
            raise ValueError("CRDB_DATABASE_URL is required to use SecretStore")
        if not _HAS_PSYCOPG2:
            raise ImportError("psycopg2 is required for CockroachDB connection. Install psycopg2-binary or use SQLite fallback.")

    @contextmanager
    def connect(self) -> Iterator[Any]:
        conn = _psycopg2.connect(self.bootstrap.crdb_dsn)
        try:
            yield conn
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_secrets (
                  key STRING PRIMARY KEY,
                  value STRING NOT NULL,
                  category STRING NOT NULL DEFAULT 'credential',
                  updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            conn.commit()

    def upsert(self, key: str, value: str, category: str = "credential") -> None:
        if not value:
            return
        encrypted_value = _encrypt(value)
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO app_secrets (key, value, category, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                  value = EXCLUDED.value,
                  category = EXCLUDED.category,
                  updated_at = EXCLUDED.updated_at
                """,
                (key, encrypted_value, category, datetime.now(timezone.utc)),
            )
            conn.commit()

    def upsert_many(self, items: dict[str, str], category: str = "credential") -> list[str]:
        saved = []
        for key, value in items.items():
            if value:
                self.upsert(key, value, category=category)
                saved.append(key)
        return saved

    def get(self, key: str, default: str = "") -> str:
        with self.connect() as conn:
            cur = conn.cursor(cursor_factory=_psycopg2_extras.RealDictCursor)
            cur.execute("SELECT value FROM app_secrets WHERE key = %s", (key,))
            row = cur.fetchone()
            if not row:
                return default
            raw = str(row["value"])
            return _decrypt(raw)

    def load_all(self) -> dict[str, str]:
        with self.connect() as conn:
            cur = conn.cursor(cursor_factory=_psycopg2_extras.RealDictCursor)
            cur.execute("SELECT key, value FROM app_secrets")
            rows = cur.fetchall()
        result = {}
        for r in rows:
            key = str(r["key"])
            try:
                result[key] = _decrypt(str(r["value"]))
            except Exception:
                result[key] = str(r["value"])
        return result

    def list_keys(self) -> list[str]:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT key FROM app_secrets ORDER BY key")
            return [r[0] for r in cur.fetchall()]


def collect_secrets_from_env() -> dict[str, str]:
    import os

    items: dict[str, str] = {}
    aliases_map = {
        "GITHUB_TOKEN": ("GITHUB_TOKEN", "GITHUB_PAT", "GITHUB_PUSH_TOKEN"),
        "DEEPSEEK_API_KEY": ("DEEPSEEK_API_KEY",),
        "CRDB_SSL_ROOT_CERT": ("CRDB_SSL_ROOT_CERT",),
        "CRDB_CLUSTER_ID": ("CRDB_CLUSTER_ID",),
        "CRDB_DATABASE_URL": ("CRDB_DATABASE_URL",),
        "POTATO_API_KEY": ("POTATO_API_KEY",),
        "POTATO_LLM_MODEL": ("POTATO_LLM_MODEL",),
        "POTATO_TRADING_MODE": ("POTATO_TRADING_MODE",),
        "ZEABUR_API_KEY": ("ZEABUR_API_KEY",),
        "ZEABUR_PROJECT_ID": ("ZEABUR_PROJECT_ID",),
        "ZEABUR_SERVICE_ID": ("ZEABUR_SERVICE_ID",),
        "ZEABUR_ENVIRONMENT_ID": ("ZEABUR_ENVIRONMENT_ID",),
        "GITHUB_REPO": ("GITHUB_REPO",),
        "TELEGRAM_BOT_TOKEN": ("TELEGRAM_BOT_TOKEN",),
        "TELEGRAM_CHAT_ID": ("TELEGRAM_CHAT_ID",),
        "DINGTALK_WEBHOOK_URL": ("DINGTALK_WEBHOOK_URL",),
        "DINGTALK_SECRET": ("DINGTALK_SECRET",),
        "FEISHU_WEBHOOK_URL": ("FEISHU_WEBHOOK_URL",),
        "FEISHU_APP_ID": ("FEISHU_APP_ID",),
        "FEISHU_APP_SECRET": ("FEISHU_APP_SECRET",),
        "FEISHU_RECEIVE_ID": ("FEISHU_RECEIVE_ID",),
        "FEISHU_API_BASE": ("FEISHU_API_BASE",),
        "POTATO_NOTIFY_ENABLED": ("POTATO_NOTIFY_ENABLED",),
        "POTATO_NOTIFY_CHANNELS": ("POTATO_NOTIFY_CHANNELS",),
        "POTATO_MAX_SINGLE_CNY": ("POTATO_MAX_SINGLE_CNY",),
        "POTATO_MAX_DAILY_CNY": ("POTATO_MAX_DAILY_CNY",),
        "POTATO_DEFAULT_ORDER_SIZE_CNY": ("POTATO_DEFAULT_ORDER_SIZE_CNY",),
    }
    for key in SECRET_KEYS:
        aliases = aliases_map.get(key, (key,))
        for alias in aliases:
            val = os.getenv(alias, "").strip()
            if val:
                items[key] = val
                break
    crdb_url = os.getenv("CRDB_DATABASE_URL", "").strip()
    if crdb_url:
        items["CRDB_DATABASE_URL"] = crdb_url
    return items


def secrets_env_fallback_enabled() -> bool:
    """When CRDB is unavailable, default to reading secrets from env vars."""
    import os

    explicit = os.getenv("POTATO_SECRETS_ENV_FALLBACK", "").lower()
    if explicit in {"1", "true", "yes"}:
        return True
    if explicit in {"0", "false", "no"}:
        return False
    bootstrap = load_bootstrap_settings()
    return not bool(bootstrap.crdb_dsn)


def _load_vault_secrets() -> dict[str, str]:
    """Load secrets from SQLite vault table (Fernet(AES-128-CBC+HMAC-SHA256) decrypted)."""
    import sqlite3
    from pathlib import Path

    db_path = Path(__file__).resolve().parents[1] / "data" / "potato.db"
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM vault")
        rows = cur.fetchall()
        conn.close()
    except Exception:
        return {}
    result: dict[str, str] = {}
    for key, value in rows:
        try:
            result[key] = _decrypt(value)
        except Exception:
            result[key] = value
    return result


def load_db_secrets() -> dict[str, str]:
    """Load all key/value pairs from app_secrets (CRDB) or vault (SQLite)."""
    bootstrap = load_bootstrap_settings()
    if not bootstrap.crdb_dsn:
        return _load_vault_secrets()
    try:
        store = SecretStore(bootstrap)
        store.ensure_schema()
        return store.load_all()
    except Exception:
        return _load_vault_secrets()


def resolve_secret(key: str, secrets: dict[str, str], *env_names: str, default: str = "") -> str:
    """Resolve a secret: CockroachDB app_secrets first; env only if POTATO_SECRETS_ENV_FALLBACK=true."""
    import os

    if key not in BOOTSTRAP_ENV_KEYS:
        db_val = secrets.get(key, "")
        if db_val:
            return db_val

    if secrets_env_fallback_enabled():
        for name in env_names:
            val = os.getenv(name)
            if val:
                return val

    if key in BOOTSTRAP_ENV_KEYS:
        for name in env_names:
            val = os.getenv(name)
            if val:
                return val

    return default