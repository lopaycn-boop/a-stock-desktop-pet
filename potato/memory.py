"""CockroachDB-backed persistent memory system for 小土豆.

Memory tiers:
- HOT (0-15 days):  Full fidelity, always injected into AI context
- WARM (15-30 days): Compressed summaries, loaded on relevant queries
- EXPIRED (>30 days): Auto-purged by daily cleanup

Tables:
- memory_episodes: Conversations, events, user statements (timestamped)
- memory_facts: Persistent user facts (name, preferences, key info)
- memory_summaries: Daily/weekly compressed summaries for long-term recall

Supports both CockroachDB (production) and SQLite (local fallback).
Compatible with CockroachDB MCP plugin (cockroachdb-toolbox).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from potato.bootstrap_config import load_bootstrap_settings
from potato.db import Database

logger = logging.getLogger("potato.memory")

HOT_DAYS = 15
WARM_DAYS = 30


class MemoryStore:
    """Persistent memory backed by CockroachDB / SQLite."""

    def __init__(self, settings=None):
        self.db = Database(settings)
        self._ensure_schema()

    def _ensure_schema(self):
        with self.db.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS memory_episodes (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'conversation',
                    importance INTEGER NOT NULL DEFAULT 5,
                    tags TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_facts (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    source TEXT DEFAULT 'user',
                    confidence REAL DEFAULT 1.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS memory_summaries (
                    id TEXT PRIMARY KEY,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    episode_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """) if hasattr(conn, 'executescript') else None

            if not hasattr(conn, 'executescript'):
                cur = conn.cursor()
                for stmt in [
                    """CREATE TABLE IF NOT EXISTS memory_episodes (
                        id STRING PRIMARY KEY,
                        content STRING NOT NULL,
                        category STRING NOT NULL DEFAULT 'conversation',
                        importance INT NOT NULL DEFAULT 5,
                        tags JSONB DEFAULT '[]',
                        created_at TIMESTAMPTZ NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL
                    )""",
                    """CREATE TABLE IF NOT EXISTS memory_facts (
                        key STRING PRIMARY KEY,
                        value STRING NOT NULL,
                        source STRING DEFAULT 'user',
                        confidence FLOAT DEFAULT 1.0,
                        created_at TIMESTAMPTZ DEFAULT now(),
                        updated_at TIMESTAMPTZ DEFAULT now()
                    )""",
                    """CREATE TABLE IF NOT EXISTS memory_summaries (
                        id STRING PRIMARY KEY,
                        period_start DATE NOT NULL,
                        period_end DATE NOT NULL,
                        summary STRING NOT NULL,
                        episode_count INT DEFAULT 0,
                        created_at TIMESTAMPTZ DEFAULT now()
                    )""",
                ]:
                    cur.execute(stmt)
                conn.commit()

    # ── Episodes (conversations, events) ──

    def store_episode(
        self,
        content: str,
        category: str = "conversation",
        importance: int = 5,
        tags: list[str] | None = None,
        ttl_days: int = WARM_DAYS,
    ) -> str:
        """Store a memory episode with automatic expiration."""
        episode_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=ttl_days)

        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO memory_episodes
                   (id, content, category, importance, tags, created_at, expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    episode_id,
                    content,
                    category,
                    importance,
                    json.dumps(tags or []),
                    now.isoformat() if self.db._use_sqlite else now,
                    expires.isoformat() if self.db._use_sqlite else expires,
                ),
            )
            conn.commit()
        logger.info("Stored episode [%s] importance=%d ttl=%dd", category, importance, ttl_days)
        return episode_id

    def get_hot_memories(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent HOT memories (< 15 days old)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=HOT_DAYS)
        cutoff_val = cutoff.isoformat() if self.db._use_sqlite else cutoff

        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT id, content, category, importance, tags, created_at
                   FROM memory_episodes
                   WHERE created_at > %s
                   ORDER BY importance DESC, created_at DESC
                   LIMIT %s""",
                (cutoff_val, limit),
            )
            rows = cur.fetchall()
        return [dict(r) if isinstance(r, dict) else r for r in rows] if rows else []

    def get_warm_memories(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get WARM memories (15-30 days old)."""
        now = datetime.now(timezone.utc)
        hot_cutoff = now - timedelta(days=HOT_DAYS)
        warm_cutoff = now - timedelta(days=WARM_DAYS)

        hot_val = hot_cutoff.isoformat() if self.db._use_sqlite else hot_cutoff
        warm_val = warm_cutoff.isoformat() if self.db._use_sqlite else warm_cutoff

        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT id, content, category, importance, tags, created_at
                   FROM memory_episodes
                   WHERE created_at <= %s AND created_at > %s
                   ORDER BY importance DESC, created_at DESC
                   LIMIT %s""",
                (hot_val, warm_val, limit),
            )
            rows = cur.fetchall()
        return [dict(r) if isinstance(r, dict) else r for r in rows] if rows else []

    def search_memories(self, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search memories by keyword (full-text)."""
        pattern = f"%{keyword}%"
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT id, content, category, importance, created_at
                   FROM memory_episodes
                   WHERE content LIKE %s
                   ORDER BY importance DESC, created_at DESC
                   LIMIT %s""",
                (pattern, limit),
            )
            rows = cur.fetchall()
        return [dict(r) if isinstance(r, dict) else r for r in rows] if rows else []

    # ── Facts (persistent user knowledge) ──

    def set_fact(self, key: str, value: str, source: str = "user", confidence: float = 1.0):
        """Store or update a persistent fact about the user."""
        now = datetime.now(timezone.utc)
        now_val = now.isoformat() if self.db._use_sqlite else now

        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT key FROM memory_facts WHERE key = %s", (key,))
            if cur.fetchone():
                cur.execute(
                    """UPDATE memory_facts
                       SET value = %s, source = %s, confidence = %s, updated_at = %s
                       WHERE key = %s""",
                    (value, source, confidence, now_val, key),
                )
            else:
                cur.execute(
                    """INSERT INTO memory_facts (key, value, source, confidence, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (key, value, source, confidence, now_val, now_val),
                )
            conn.commit()
        logger.info("Fact set: %s = %s (source=%s)", key, value[:50], source)

    def get_all_facts(self) -> dict[str, str]:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT key, value FROM memory_facts ORDER BY key")
            rows = cur.fetchall()
        if not rows:
            return {}
        return {r["key"]: r["value"] for r in rows} if isinstance(rows[0], dict) else {}

    def get_fact(self, key: str, default: str = "") -> str:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM memory_facts WHERE key = %s", (key,))
            row = cur.fetchone()
        return row["value"] if row else default

    # ── Summaries (compressed long-term) ──

    def store_summary(self, period_start: date, period_end: date, summary: str, episode_count: int = 0) -> str:
        summary_id = str(uuid.uuid4())
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO memory_summaries
                   (id, period_start, period_end, summary, episode_count)
                   VALUES (%s, %s, %s, %s, %s)""",
                (
                    summary_id,
                    period_start.isoformat() if self.db._use_sqlite else period_start,
                    period_end.isoformat() if self.db._use_sqlite else period_end,
                    summary,
                    episode_count,
                ),
            )
            conn.commit()
        return summary_id

    def get_recent_summaries(self, limit: int = 5) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM memory_summaries ORDER BY period_end DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
        return [dict(r) if isinstance(r, dict) else r for r in rows] if rows else []

    # ── Cleanup (30-day expiration) ──

    def cleanup_expired(self) -> dict[str, int]:
        """Delete episodes older than 30 days. Compress 15-30 day episodes into summaries."""
        now = datetime.now(timezone.utc)
        expire_cutoff = now - timedelta(days=WARM_DAYS)
        expire_val = expire_cutoff.isoformat() if self.db._use_sqlite else expire_cutoff

        with self.db.connect() as conn:
            cur = conn.cursor()

            cur.execute(
                "SELECT COUNT(*) as cnt FROM memory_episodes WHERE created_at <= %s",
                (expire_val,),
            )
            row = cur.fetchone()
            expired_count = row["cnt"] if isinstance(row, dict) else (row[0] if row else 0)

            if expired_count > 0:
                cur.execute(
                    "SELECT content, category FROM memory_episodes WHERE created_at <= %s ORDER BY created_at",
                    (expire_val,),
                )
                old_episodes = cur.fetchall()

                if old_episodes:
                    period_start = (now - timedelta(days=WARM_DAYS + 7)).date()
                    period_end = (now - timedelta(days=WARM_DAYS)).date()
                    summary_lines = []
                    for ep in old_episodes[:20]:
                        ep_dict = dict(ep) if isinstance(ep, dict) else {"content": ep[0], "category": ep[1]}
                        summary_lines.append(f"[{ep_dict.get('category', '')}] {ep_dict['content'][:100]}")
                    summary_text = "\n".join(summary_lines)
                    self.store_summary(period_start, period_end, summary_text, len(old_episodes))

                cur.execute("DELETE FROM memory_episodes WHERE created_at <= %s", (expire_val,))
                conn.commit()

        logger.info("Memory cleanup: %d expired episodes processed", expired_count)
        return {"expired_deleted": expired_count}

    # ── Context building (for AI system prompt) ──

    def build_memory_context(self, user_input: str = "") -> str:
        """Build memory context string for injection into AI system prompt."""
        sections = []

        facts = self.get_all_facts()
        if facts:
            facts_str = "\n".join(f"  - {k}: {v}" for k, v in facts.items())
            sections.append(f"【已知用户信息】\n{facts_str}")

        hot = self.get_hot_memories(limit=15)
        if hot:
            hot_lines = []
            for m in hot:
                m_dict = dict(m) if isinstance(m, dict) else m
                content = m_dict.get("content", "")[:150]
                cat = m_dict.get("category", "")
                hot_lines.append(f"  - [{cat}] {content}")
            sections.append(f"【近期记忆 (15天内)】\n" + "\n".join(hot_lines))

        warm = self.get_warm_memories(limit=5)
        if warm:
            warm_lines = []
            for m in warm:
                m_dict = dict(m) if isinstance(m, dict) else m
                content = m_dict.get("content", "")[:100]
                warm_lines.append(f"  - {content}")
            sections.append(f"【较早记忆 (15-30天)】\n" + "\n".join(warm_lines))

        if user_input:
            related = self.search_memories(user_input[:30], limit=3)
            if related:
                rel_lines = []
                for m in related:
                    m_dict = dict(m) if isinstance(m, dict) else m
                    rel_lines.append(f"  - {m_dict.get('content', '')[:120]}")
                sections.append(f"【相关记忆】\n" + "\n".join(rel_lines))

        summaries = self.get_recent_summaries(limit=2)
        if summaries:
            sum_lines = []
            for s in summaries:
                s_dict = dict(s) if isinstance(s, dict) else s
                sum_lines.append(f"  [{s_dict.get('period_start', '')}~{s_dict.get('period_end', '')}] "
                                 f"{s_dict.get('summary', '')[:200]}")
            sections.append(f"【历史摘要】\n" + "\n".join(sum_lines))

        if not sections:
            return "（暂无记忆）"

        return "\n\n".join(sections)

    def process_ai_memory_ops(self, memory_operation: dict[str, Any]):
        """Process memory operations returned by AI in conversation."""
        if not memory_operation:
            return

        new_facts = memory_operation.get("new_facts")
        if new_facts and isinstance(new_facts, dict):
            for k, v in new_facts.items():
                self.set_fact(k, str(v), source="ai_extracted")

        new_episode = memory_operation.get("new_episode")
        if new_episode and isinstance(new_episode, str):
            importance = memory_operation.get("importance", 5)
            category = memory_operation.get("category", "conversation")
            self.store_episode(new_episode, category=category, importance=importance)
