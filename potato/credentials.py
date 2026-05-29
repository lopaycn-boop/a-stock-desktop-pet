"""CredentialsPlugin — DB-backed platform credential storage + permission model.

Two modes per platform:
  - AUTONOMOUS: user gave credentials (account/password/API key),
    stored Fernet(AES-128-CBC+HMAC-SHA256) encrypted in DB → 小土豆 logs in + trades fully autonomously.
  - ASSISTED: no credentials stored → user logs in via desktop pet/browser,
    then 小土豆 takes over to operate on the logged-in session.

The credential plugin is the single authority for deciding which mode a platform
is in. browser_cycle reads it; the desktop pet reads it; the API exposes it.

Security: values are encrypted at rest using Fernet(AES-128-CBC+HMAC-SHA256).
  Key is derived from machine fingerprint + per-installation salt.
  Falls back to base64 encoding if cryptography package is unavailable (NOT secure).
  This is NOT the same as vault.py encoding — each module uses its own _encode/_decode
  wrapper but both delegate to the centralized encryption in vault module.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from potato.db import Database
from potato.vault import _encrypt, _decrypt, _get_cipher

logger = logging.getLogger("potato.credentials")

CRED_FIELDS = {
    "eastmoney": {
        "account": {"label": "东方财富账号", "required": True},
        "password": {"label": "东方财富密码", "required": True, "sensitive": True},
    },
    "tonghuashun": {
        "account": {"label": "同花顺账号", "required": True},
        "password": {"label": "同花顺密码", "required": True, "sensitive": True},
    },
    "xueqiu": {
        "account": {"label": "雪球账号/手机号", "required": True},
        "password": {"label": "雪球密码", "required": True, "sensitive": True},
    },
}

_CRED_FIELDS_FLAT = CRED_FIELDS


@dataclass
class PlatformCredential:
    platform_id: str
    fields: dict[str, str] = field(default_factory=dict)
    autonomous: bool = False
    granted_at: str = ""
    last_used_at: str = ""


class CredentialsPlugin:
    """Database-backed credential store with permission model.

    Table: platform_credentials
      - platform_id (PK)
      - encoded_fields (Fernet-encrypted JSON blob)
      - autonomous (bool)
      - granted_at, last_used_at

    Security: values are encrypted using Fernet(AES-128-CBC+HMAC-SHA256) at rest.
    Requires cryptography package for production use.
    """

    def __init__(self, settings=None):
        self.db = Database(settings)
        self._ensure_table()

    def _ensure_table(self):
        with self.db.connect() as conn:
            if hasattr(conn, "executescript"):
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS platform_credentials (
                        platform_id TEXT PRIMARY KEY,
                        encoded_fields TEXT NOT NULL DEFAULT '{}',
                        autonomous INTEGER NOT NULL DEFAULT 0,
                        granted_at TEXT DEFAULT '',
                        last_used_at TEXT DEFAULT ''
                    );
                """)
            else:
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS platform_credentials (
                        platform_id STRING PRIMARY KEY,
                        encoded_fields STRING NOT NULL DEFAULT '{}',
                        autonomous BOOL NOT NULL DEFAULT false,
                        granted_at TIMESTAMPTZ DEFAULT now(),
                        last_used_at TIMESTAMPTZ DEFAULT now()
                    )
                """)
                conn.commit()

    def grant(self, platform_id: str, credentials: dict[str, str]) -> dict[str, Any]:
        """Store credentials for a platform → switches to AUTONOMOUS mode.

        The user explicitly gives their account/password/API key.
        小土豆 can now log in and trade without user interaction.
        """
        now = datetime.now(timezone.utc)
        now_val = now.isoformat() if self.db._use_sqlite else now
        encoded = _encrypt(json.dumps(credentials, ensure_ascii=False))

        encryption_active = _get_cipher() is not None and _get_cipher() != "FALLBACK"
        if not encryption_active:
            logger.warning(
                "Credentials stored WITHOUT proper encryption (cryptography package missing). "
                "Install with: pip install cryptography"
            )

        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT platform_id FROM platform_credentials WHERE platform_id = %s", (platform_id,))
            if cur.fetchone():
                cur.execute(
                    "UPDATE platform_credentials SET encoded_fields=%s, autonomous=1, granted_at=%s, last_used_at=%s WHERE platform_id=%s",
                    (encoded, now_val, now_val, platform_id),
                )
            else:
                cur.execute(
                    "INSERT INTO platform_credentials (platform_id, encoded_fields, autonomous, granted_at, last_used_at) VALUES (%s,%s,1,%s,%s)",
                    (platform_id, encoded, now_val, now_val),
                )
            conn.commit()

        logger.info("Credentials granted for %s — AUTONOMOUS mode", platform_id)
        return {
            "ok": True,
            "platform_id": platform_id,
            "mode": "autonomous",
            "fields_stored": list(credentials.keys()),
        }

    def revoke(self, platform_id: str) -> dict[str, Any]:
        """Remove credentials → switches back to ASSISTED mode.

        User revokes permission; 小土豆 can no longer log in automatically.
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM platform_credentials WHERE platform_id = %s", (platform_id,))
            conn.commit()

        logger.info("Credentials revoked for %s — ASSISTED mode", platform_id)
        return {"ok": True, "platform_id": platform_id, "mode": "assisted"}

    def get(self, platform_id: str) -> PlatformCredential | None:
        """Get credential record for a platform (decodes values)."""
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT platform_id, encoded_fields, autonomous, granted_at, last_used_at FROM platform_credentials WHERE platform_id = %s",
                (platform_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        d = dict(row) if isinstance(row, dict) else {}
        raw = d.get("encoded_fields", "{}")
        if not isinstance(raw, str):
            raw = "{}"
        try:
            fields = json.loads(_decrypt(raw))
        except Exception:
            fields = {}
        auto_val = d.get("autonomous", 0)
        autonomous = bool(auto_val) if not isinstance(auto_val, bool) else auto_val
        return PlatformCredential(
            platform_id=d.get("platform_id", platform_id),
            fields=fields,
            autonomous=autonomous,
            granted_at=str(d.get("granted_at", "")),
            last_used_at=str(d.get("last_used_at", "")),
        )

    def get_decoded_credentials(self, platform_id: str) -> dict[str, str]:
        """Get decoded credentials for browser login (only if autonomous)."""
        cred = self.get(platform_id)
        if cred and cred.autonomous:
            return cred.fields
        return {}

    def touch_used(self, platform_id: str) -> None:
        now = datetime.now(timezone.utc)
        now_val = now.isoformat() if self.db._use_sqlite else now
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE platform_credentials SET last_used_at=%s WHERE platform_id=%s",
                (now_val, platform_id),
            )
            conn.commit()

    def list_all(self) -> list[PlatformCredential]:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT platform_id, encoded_fields, autonomous, granted_at, last_used_at FROM platform_credentials ORDER BY platform_id"
            )
            rows = cur.fetchall()
        result = []
        for r in (rows or []):
            d = dict(r) if isinstance(r, dict) else {}
            pid = d.get("platform_id", "")
            raw = d.get("encoded_fields", "{}")
            try:
                fields = json.loads(_decrypt(raw))
            except Exception:
                fields = {}
            auto_val = d.get("autonomous", 0)
            autonomous = bool(auto_val) if not isinstance(auto_val, bool) else auto_val
            result.append(PlatformCredential(
                platform_id=pid,
                fields=fields,
                autonomous=autonomous,
                granted_at=str(d.get("granted_at", "")),
                last_used_at=str(d.get("last_used_at", "")),
            ))
        return result

    def permission_status(self) -> dict[str, Any]:
        """Summary of all platforms: which mode they're in.

        NOTE: This deliberately does NOT return credential values.
        Only returns metadata (field names, modes, timestamps).
        """
        creds = self.list_all()
        encryption_active = _get_cipher() is not None and _get_cipher() != "FALLBACK"
        status = {}
        for c in creds:
            status[c.platform_id] = {
                "mode": "autonomous" if c.autonomous else "assisted",
                "has_credentials": bool(c.fields),
                "fields": [k for k in c.fields.keys()],
                "granted_at": c.granted_at,
                "last_used_at": c.last_used_at,
            }
        return {
            "platforms": status,
        }

    @staticmethod
    def field_schema(platform_id: str) -> dict[str, dict[str, Any]]:
        """Return the expected credential fields for a platform."""
        return _CRED_FIELDS_FLAT.get(platform_id, {})

    @staticmethod
    def all_field_schemas() -> dict[str, dict[str, dict[str, Any]]]:
        return _CRED_FIELDS_FLAT