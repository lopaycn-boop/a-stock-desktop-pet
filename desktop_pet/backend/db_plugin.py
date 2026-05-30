"""Unified database plugin for desktop pet.

Initializes ALL tables in a single place, bridges the desktop pet Config
with the potato.db.Database system, and makes CRDB/psycopg2 fully optional.

Database layout (SQLite fallback path):
    data/potato.db    — markets, positions, orders, agent_decisions,
                        risk_limits, cycle_runs, app_secrets,
                        platform_credentials, vault,
                        memory_episodes, memory_facts, memory_summaries
    backend/memory_db/ — ChromaDB vector store for episodic embeddings
    backend/user_facts.json — simple fact store (legacy, desktop pet)
    data/user_prefs.json — user preference store
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from potato.paths import DATA_DIR

logger = logging.getLogger("potato.pet.db")

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parents[1]

_db_instance = None


def get_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def get_db() -> "Database":
    global _db_instance
    if _db_instance is None:
        from potato.db import Database
        settings = _build_settings()
        _db_instance = Database(settings)
    return _db_instance


def _build_settings():
    try:
        from potato.config import load_settings
        settings = load_settings(use_db_secrets=False)
        return settings
    except Exception:
        pass

    try:
        from potato.bootstrap_config import load_bootstrap_settings
        bootstrap = load_bootstrap_settings()
        if bootstrap.crdb_dsn:
            return bootstrap
    except Exception:
        pass

    return None


def init_db() -> dict[str, Any]:
    """Initialize ALL database tables. Safe to call multiple times (idempotent).

    Creates:
    1. data/ directory and user_prefs.json defaults
    2. Core trading tables (markets, positions, orders, etc.)
    3. Vault table (secret storage)
    4. Platform credentials table
    5. Memory tables (episodes, facts, summaries)
    6. ChromaDB directory for vector memory
    """
    results: dict[str, Any] = {}
    get_data_dir()
    (BACKEND_DIR / "memory_db").mkdir(parents=True, exist_ok=True)

    try:
        db = get_db()
        core_result = db.init_schema()
        results["core_tables"] = core_result
        logger.info("Core tables initialized: %s", core_result)
    except Exception as e:
        logger.warning("Core table init failed (non-fatal for desktop pet): %s", e)
        results["core_tables_error"] = str(e)

    try:
        from potato.vault import Vault
        vault = Vault(settings=_build_settings())
        results["vault"] = {"ok": True, "backend": vault.db.backend}
        logger.info("Vault table ready (backend=%s)", vault.db.backend)
    except Exception as e:
        logger.warning("Vault init failed (non-fatal): %s", e)
        results["vault_error"] = str(e)

    try:
        from potato.credentials import CredentialsPlugin
        cred = CredentialsPlugin(settings=_build_settings())
        results["credentials"] = {"ok": True, "backend": cred.db.backend}
        logger.info("Credentials table ready (backend=%s)", cred.db.backend)
    except Exception as e:
        logger.warning("Credentials init failed (non-fatal): %s", e)
        results["credentials_error"] = str(e)

    try:
        from potato.memory import MemoryStore
        mem = MemoryStore(settings=_build_settings())
        results["memory"] = {"ok": True, "backend": mem.db.backend}
        logger.info("Memory tables ready (backend=%s)", mem.db.backend)
    except Exception as e:
        logger.warning("MemoryStore init failed (non-fatal): %s", e)
        results["memory_error"] = str(e)

    try:
        facts_path = BACKEND_DIR / "user_facts.json"
        if not facts_path.exists():
            import json
            facts_path.write_text("{}", encoding="utf-8")
            logger.info("Created user_facts.json")
    except Exception as e:
        logger.warning("Failed to create user_facts.json: %s", e)

    try:
        prefs_path = DATA_DIR / "user_prefs.json"
        if not prefs_path.exists():
            import json
            prefs_path.write_text(
                '{"sectors":[],"watchlist":[],"custom_queries":[],'
                '"risk_level":"conservative","max_single_trade_cny":300,'
                '"max_daily_trade_cny":1500,"preferred_markets":[],'
                '"language":"zh-CN","daily_briefing_enabled":true,'
                '"auto_trade_enabled":false,"notes":"","updated_at":""}',
                encoding="utf-8",
            )
            logger.info("Created user_prefs.json defaults")
    except Exception as e:
        logger.warning("Failed to create user_prefs.json: %s", e)

    logger.info("Database initialization complete: %s", list(results.keys()))
    return results


def health_check() -> dict[str, Any]:
    """Quick health check — can the DB be reached?"""
    status: dict[str, Any] = {"ok": True}
    try:
        db = get_db()
        with db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        status["database"] = db.backend
    except Exception as e:
        status["ok"] = False
        status["database_error"] = str(e)

    try:
        from potato.vault import Vault
        vault = Vault(settings=_build_settings())
        vault_status = vault.status()
        status["vault_keys"] = vault_status.get("total_keys", 0)
    except Exception as e:
        status["vault_error"] = str(e)

    try:
        from potato.credentials import CredentialsPlugin
        cred = CredentialsPlugin(settings=_build_settings())
        perm = cred.permission_status()
        status["credential_platforms"] = len(perm)
    except Exception as e:
        status["credentials_error"] = str(e)

    try:
        chroma_path = BACKEND_DIR / "memory_db"
        status["chroma_dir_exists"] = chroma_path.exists()
        status["facts_file_exists"] = (BACKEND_DIR / "user_facts.json").exists()
        status["prefs_file_exists"] = (DATA_DIR / "user_prefs.json").exists()
    except Exception as e:
        status["files_error"] = str(e)

    return status