"""Vault — 小土豆的密钥保险箱。

用户通过桌宠给密钥，小土豆存入数据库，拿到密钥就能操作对应平台。

存储层：SQLite (本地) / CockroachDB (云端)，与现有 DB 共用。
安全：密钥存储时 Fernet(AES-128-CBC + HMAC-SHA256) 加密，读取时自动解密。
  加密密钥派生自机器指纹 + 用户密钥盐，每台机器不同。
  无明文存储，解密失败直接报错不回退明文。
分类：platform_credentials / api_keys / bot_tokens / user_secrets

用法：
  用户: "我的富途账号是 xxx，密码是 xxx"
  小土豆: AI 提取 -> vault.store() -> 下次自动登录
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
from datetime import datetime, timezone
from typing import Any

from potato.db import Database

logger = logging.getLogger("potato.vault")

VAULT_CATEGORIES = {
    "platform": "交易平台凭证（账号密码/API Key）",
    "api_key": "第三方 API 密钥（DeepSeek/SiliconFlow 等）",
    "bot_token": "社交平台机器人 Token（Telegram/飞书/钉钉）",
    "user": "用户自定义密钥",
}

KNOWN_KEYS = {
    "DEEPSEEK_API_KEY": {"category": "api_key", "desc": "DeepSeek 大模型 API Key", "required": True,
                          "renewal_url": "https://platform.deepseek.com/usage", "dashboard_url": "https://platform.deepseek.com/api_keys"},
    "SILICON_API_KEY": {"category": "api_key", "desc": "SiliconFlow LLM API Key (sk-... 格式)",
                         "renewal_url": "https://cloud.siliconflow.cn/account/usage", "dashboard_url": "https://cloud.siliconflow.cn/account/token"},
    "SILICONFLOW_API_KEY": {"category": "api_key", "desc": "SiliconFlow LLM API Key (别名，等同SILICON_API_KEY)",
                             "renewal_url": "https://cloud.siliconflow.cn/account/usage", "dashboard_url": "https://cloud.siliconflow.cn/account/token"},
    "LINER_API_KEY": {"category": "api_key", "desc": "Liner AI API Key (4层故障转移)",
                      "renewal_url": "https://platform.liner.com/keys", "dashboard_url": "https://platform.liner.com/keys"},
    "OPENAI_API_KEY": {"category": "api_key", "desc": "OpenAI API Key (4层故障转移)",
                       "renewal_url": "https://platform.openai.com/account/billing", "dashboard_url": "https://platform.openai.com/api-keys"},
    "BASE44_API_KEY": {"category": "api_key", "desc": "Base44 AI Agent API Key (5层故障转移)",
                       "renewal_url": "https://app.base44.com", "dashboard_url": "https://app.base44.com"},
    "TELEGRAM_BOT_TOKEN": {"category": "bot_token", "desc": "Telegram 机器人 Token"},
    "TELEGRAM_CHAT_ID": {"category": "bot_token", "desc": "Telegram 聊天 ID"},
    "FEISHU_APP_ID": {"category": "bot_token", "desc": "飞书应用 ID"},
    "FEISHU_APP_SECRET": {"category": "bot_token", "desc": "飞书应用密钥"},
    "DINGTALK_WEBHOOK_URL": {"category": "bot_token", "desc": "钉钉 Webhook URL"},
    "EASTMONEY_ACCOUNT": {"category": "platform", "desc": "东方财富账号"},
    "EASTMONEY_PASSWORD": {"category": "platform", "desc": "东方财富密码"},
    "TONGHUASHUN_ACCOUNT": {"category": "platform", "desc": "同花顺账号"},
    "TONGHUASHUN_PASSWORD": {"category": "platform", "desc": "同花顺密码"},
    "XUEQIU_TOKEN": {"category": "platform", "desc": "雪球登录 Token/Cookie"},
    "HTSEC_ACCOUNT": {"category": "platform", "desc": "华泰证券账号（XTP量化交易）"},
    "HTSEC_PASSWORD": {"category": "platform", "desc": "华泰证券密码"},
    "BROKER_ID": {"category": "platform", "desc": "券商标识: eastmoney/ths/htsec（默认eastmoney）"},
    "TRADING_MODE": {"category": "platform", "desc": "交易模式: dry_run(模拟)/live(实盘)（默认dry_run）"},
    "BYTEBOT_AGENT_URL": {"category": "bytebot", "desc": "Bytebot AI Agent 地址 (如 http://localhost:9991)"},
    "BYTEBOT_DESKTOP_URL": {"category": "bytebot", "desc": "Bytebot Desktop Daemon 地址 (如 http://localhost:9990)"},
    "PLATFORM_WALLET_ADDRESS": {"category": "billing", "desc": "平台数字币收款地址（续费时显示）", "renewal_only": True},
    "ANTHROPIC_API_KEY": {"category": "api_key", "desc": "Anthropic Claude API Key (Bytebot)",
                          "renewal_url": "https://console.anthropic.com/settings/billing", "dashboard_url": "https://console.anthropic.com/settings/keys"},
}

_CIPHER = None


def _get_vault_key() -> bytes:
    """Derive a 256-bit encryption key for vault encryption.

    Priority:
    1. VAULT_ENCRYPTION_KEY env var — for production (set in Zeabur env)
    2. Machine fingerprint + salt file — for desktop (local dev)

    On production servers (Zeabur), VAULT_ENCRYPTION_KEY MUST be set to a stable
    value. Without it, container rebuilds change the hostname and make all
    previously encrypted data undecryptable.
    """
    from pathlib import Path

    env_key = os.getenv("VAULT_ENCRYPTION_KEY", "").strip()
    if env_key:
        salt_val = os.environ.get("VAULT_SALT", "").strip()
        if not salt_val:
            logger.warning("VAULT_ENCRYPTION_KEY set but VAULT_SALT not set — using insecure default salt. Set VAULT_SALT for production.")
            salt_val = "vault-stable-salt-CHANGE-ME-IN-PRODUCTION"
        return hashlib.pbkdf2_hmac("sha256", env_key.encode(), salt_val.encode(), 200_000)

    salt_path = Path(__file__).resolve().parents[1] / "data" / ".vault_salt"
    if salt_path.exists():
        salt = salt_path.read_bytes()
    else:
        salt = os.urandom(32)
        salt_path.parent.mkdir(parents=True, exist_ok=True)
        salt_path.write_bytes(salt)

    machine_id = f"{platform.node()}-{os.getenv('USER', os.getenv('USERNAME', 'unknown'))}"
    return hashlib.pbkdf2_hmac("sha256", machine_id.encode(), salt, 200_000)


def _get_cipher():
    """Lazy-initialize Fernet cipher. Requires cryptography package — hard fail if missing."""
    global _CIPHER
    if _CIPHER is not None:
        return _CIPHER if _CIPHER is not None else None

    try:
        from cryptography.fernet import Fernet
        key = _get_vault_key()
        fernet_key = base64.urlsafe_b64encode(key)
        _CIPHER = Fernet(fernet_key)
        return _CIPHER
    except ImportError:
        logger.error(
            "cryptography package not installed — vault encryption DISABLED. "
            "Secrets CANNOT be stored. Install with: pip install cryptography"
        )
        _CIPHER = None
        return None


def _encrypt(value: str) -> str:
    """Encrypt a value using Fernet. Raises RuntimeError if cryptography is unavailable."""
    cipher = _get_cipher()
    if cipher is None:
        raise RuntimeError(
            "Vault encryption unavailable: 'cryptography' package not installed. "
            "Refusing to store secrets unencrypted. Run: pip install cryptography"
        )
    try:
        return cipher.encrypt(value.encode("utf-8")).decode("ascii")
    except Exception as exc:
        logger.error("Vault encryption failed: %s", exc)
        raise RuntimeError(f"Vault encryption failed: {exc}") from exc


def _decrypt(encoded: str) -> str:
    """Decrypt a value using Fernet encryption.

    Raises RuntimeError if decryption fails — compromised or wrong-key data
    is never silently decoded as plaintext."""
    cipher = _get_cipher()
    if cipher is None:
        raise RuntimeError("Vault decryption failed: no encryption key available. Set VAULT_ENCRYPTION_KEY.")
    try:
        return cipher.decrypt(encoded.encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise RuntimeError(
            f"Vault decryption failed: data may be corrupted or encrypted with a different key. "
            f"Error: {exc}"
        ) from exc


class Vault:

    def __init__(self, settings=None):
        self.db = Database(settings)
        self._ensure_table()

    def _ensure_table(self):
        with self.db.connect() as conn:
            if hasattr(conn, "executescript"):
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS vault (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT 'user',
                        description TEXT DEFAULT '',
                        platform_id TEXT DEFAULT '',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                """)
            else:
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS vault (
                        key STRING PRIMARY KEY,
                        value STRING NOT NULL,
                        category STRING NOT NULL DEFAULT 'user',
                        description STRING DEFAULT '',
                        platform_id STRING DEFAULT '',
                        created_at TIMESTAMPTZ DEFAULT now(),
                        updated_at TIMESTAMPTZ DEFAULT now()
                    )
                """)
                conn.commit()

    def store(self, key: str, value: str, category: str = "", platform_id: str = "", description: str = "") -> dict[str, Any]:
        key = key.strip().upper()
        if not category:
            known = KNOWN_KEYS.get(key, {})
            category = known.get("category", "user")
        if not description:
            known = KNOWN_KEYS.get(key, {})
            description = known.get("desc", "")

        encrypted = _encrypt(value)
        now = datetime.now(timezone.utc)
        now_val = now.isoformat() if self.db._use_sqlite else now

        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT key FROM vault WHERE key = %s", (key,))
            if cur.fetchone():
                cur.execute(
                    "UPDATE vault SET value=%s, category=%s, description=%s, platform_id=%s, updated_at=%s WHERE key=%s",
                    (encrypted, category, description, platform_id, now_val, key),
                )
            else:
                cur.execute(
                    "INSERT INTO vault (key, value, category, description, platform_id, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (key, encrypted, category, description, platform_id, now_val, now_val),
                )
            conn.commit()

        logger.info("Vault stored: %s [%s] platform=%s", key, category, platform_id)
        return {"ok": True, "key": key, "category": category}

    def get(self, key: str) -> str:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM vault WHERE key = %s", (key.upper(),))
            row = cur.fetchone()
        if not row:
            return ""
        raw = row["value"] if isinstance(row, dict) else row[0]
        return _decrypt(raw)

    def delete(self, key: str) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM vault WHERE key = %s", (key.upper(),))
            conn.commit()
        logger.info("Vault deleted: %s", key)
        return True

    def list_keys(self, category: str = "") -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            cur = conn.cursor()
            if category:
                cur.execute(
                    "SELECT key, category, description, platform_id, updated_at FROM vault WHERE category=%s ORDER BY key",
                    (category,),
                )
            else:
                cur.execute("SELECT key, category, description, platform_id, updated_at FROM vault ORDER BY key")
            rows = cur.fetchall()

        result = []
        for r in (rows or []):
            d = dict(r) if isinstance(r, dict) else {}
            result.append({
                "key": d.get("key", ""),
                "category": d.get("category", ""),
                "description": d.get("description", ""),
                "platform_id": d.get("platform_id", ""),
                "has_value": True,
                "updated_at": d.get("updated_at", ""),
            })
        return result

    def get_platform_credentials(self, platform_id: str) -> dict[str, str]:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT key, value FROM vault WHERE platform_id = %s", (platform_id,))
            rows = cur.fetchall()
        creds = {}
        for r in (rows or []):
            d = dict(r) if isinstance(r, dict) else {}
            creds[d.get("key", "")] = _decrypt(d.get("value", ""))
        return creds

    def status(self) -> dict[str, Any]:
        keys = self.list_keys()
        by_cat = {}
        for k in keys:
            cat = k["category"]
            by_cat[cat] = by_cat.get(cat, 0) + 1

        missing_required = []
        for key, info in KNOWN_KEYS.items():
            if info.get("required") and not self.get(key):
                missing_required.append({"key": key, "desc": info["desc"]})

        encryption_active = _get_cipher() is not None and _get_cipher() != "FALLBACK"

        return {
            "total_keys": len(keys),
            "by_category": by_cat,
            "missing_required": missing_required,
            "categories": VAULT_CATEGORIES,
        }

    def to_context_string(self) -> str:
        keys = self.list_keys()
        if not keys:
            return "密钥保险箱为空，用户还没给任何密钥"
        lines = ["已存密钥:"]
        for k in keys:
            lines.append(f"  - {k['key']} [{k['category']}] {k['description']}")
        return "\n".join(lines)