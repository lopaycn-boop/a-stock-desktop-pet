from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from potato.bootstrap_config import BootstrapSettings, load_bootstrap_settings
from potato.paths import DATA_DIR

logger = logging.getLogger("potato.db")

try:
    import psycopg2
    import psycopg2.extras
    _HAS_PSYCOPG2 = True
except ImportError:
    psycopg2 = None
    psycopg2 = type("psycopg2", (), {"extras": type("extras", (), {"RealDictCursor": None})(), "connect": None})()
    _HAS_PSYCOPG2 = False

INJECTION_PATTERNS = [
    r"ignore (previous|all) instructions",
    r"new (task|directive|instruction)",
    r"system prompt",
    r"send .{0,50} to 0x[0-9a-fA-F]{40}",
]


def sanitize_text(text: str, max_len: int = 500) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text or "")
    cleaned = cleaned.strip()[:max_len]
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            raise ValueError("Input blocked: potential injection detected")
    return cleaned


class Database:
    def __init__(self, settings: Any | None = None, *, bootstrap: BootstrapSettings | None = None):
        if settings is not None:
            try:
                self._crdb_dsn = settings.crdb_dsn
            except (ValueError, AttributeError):
                self._crdb_dsn = getattr(settings, "crdb_url", "")
        elif bootstrap is not None:
            self._crdb_dsn = bootstrap.crdb_dsn
        else:
            boot = load_bootstrap_settings()
            self._crdb_dsn = boot.crdb_dsn
        self._use_sqlite = not bool(self._crdb_dsn)
        self._sqlite_path = DATA_DIR / "potato.db"

    @property
    def backend(self) -> str:
        return "sqlite" if self._use_sqlite else "cockroachdb"

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self._use_sqlite:
            self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._sqlite_path)
            conn.row_factory = sqlite3.Row
            try:
                yield _SQLiteConn(conn)
            finally:
                conn.close()
        else:
            if not _HAS_PSYCOPG2:
                logger.warning("psycopg2 not installed; falling back to SQLite")
                self._use_sqlite = True
                self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self._sqlite_path)
                conn.row_factory = sqlite3.Row
                try:
                    yield _SQLiteConn(conn)
                finally:
                    conn.close()
                return
            conn = psycopg2.connect(self._crdb_dsn)
            conn.autocommit = False
            try:
                yield _PgConn(conn)
            finally:
                conn.close()

    def init_schema(self) -> dict[str, Any]:
        sql_path = Path(__file__).resolve().parents[1] / "schema" / "init.sql"
        raw = sql_path.read_text(encoding="utf-8")
        if self._use_sqlite:
            return self._init_sqlite()
        statements = [s.strip() for s in raw.split(";") if s.strip()]
        executed = 0
        with self.connect() as conn:
            cur = conn.cursor()
            for stmt in statements:
                cur.execute(stmt)
                executed += 1
            conn.commit()
        return {"backend": self.backend, "statements_executed": executed}

    def _init_sqlite(self) -> dict[str, Any]:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS markets (
                  condition_id TEXT PRIMARY KEY,
                  question TEXT NOT NULL,
                  token_id_yes TEXT NOT NULL,
                  token_id_no TEXT NOT NULL,
                  price_yes REAL,
                  price_no REAL,
                  volume_24h REAL,
                  spread_pct REAL,
                  active INTEGER DEFAULT 1,
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS positions (
                  id TEXT PRIMARY KEY,
                  token_id TEXT NOT NULL,
                  condition_id TEXT,
                  side TEXT NOT NULL,
                  size REAL NOT NULL,
                  avg_entry REAL NOT NULL,
                  opened_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  closed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS orders (
                  id TEXT PRIMARY KEY,
                  client_order_id TEXT UNIQUE NOT NULL,
                  token_id TEXT NOT NULL,
                  condition_id TEXT,
                  side TEXT NOT NULL,
                  price REAL NOT NULL,
                  size REAL NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  clob_order_id TEXT,
                  dry_run INTEGER DEFAULT 0,
                  error_message TEXT,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS agent_decisions (
                  id TEXT PRIMARY KEY,
                  run_id TEXT NOT NULL,
                  action TEXT NOT NULL,
                  token_id TEXT,
                  condition_id TEXT,
                  price REAL,
                  size REAL,
                  reasoning TEXT,
                  model TEXT DEFAULT 'potato-engine',
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS risk_limits (
                  day TEXT PRIMARY KEY,
                  spent_cny REAL NOT NULL DEFAULT 0,
                  trade_count INTEGER NOT NULL DEFAULT 0,
                  circuit_breaker INTEGER NOT NULL DEFAULT 0,
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS cycle_runs (
                  run_id TEXT PRIMARY KEY,
                  status TEXT NOT NULL,
                  summary TEXT,
                  started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS app_secrets (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL,
                  category TEXT NOT NULL DEFAULT 'credential',
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS platform_credentials (
                  platform_id TEXT PRIMARY KEY,
                  encoded_fields TEXT NOT NULL DEFAULT '{}',
                  autonomous INTEGER NOT NULL DEFAULT 0,
                  granted_at TEXT DEFAULT '',
                  last_used_at TEXT DEFAULT ''
                );
                """
            )
        return {"backend": "sqlite", "path": str(self._sqlite_path)}

    def upsert_markets(self, markets: list[dict[str, Any]]) -> int:
        if not markets:
            return 0
        with self.connect() as conn:
            cur = conn.cursor()
            updated = datetime.now(timezone.utc)
            updated_val = updated.isoformat() if self._use_sqlite else updated
            for m in markets:
                cur.execute(
                    """
                    INSERT INTO markets (
                      condition_id, question, token_id_yes, token_id_no,
                      price_yes, price_no, volume_24h, spread_pct, active, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (condition_id) DO UPDATE SET
                      question = EXCLUDED.question,
                      price_yes = EXCLUDED.price_yes,
                      price_no = EXCLUDED.price_no,
                      volume_24h = EXCLUDED.volume_24h,
                      spread_pct = EXCLUDED.spread_pct,
                      active = EXCLUDED.active,
                      updated_at = EXCLUDED.updated_at
                    """,
                    (
                        m["condition_id"],
                        sanitize_text(m["question"]),
                        m["token_id_yes"],
                        m["token_id_no"],
                        m.get("price_yes"),
                        m.get("price_no"),
                        m.get("volume_24h"),
                        m.get("spread_pct"),
                        m.get("active", True),
                        updated_val,
                    ),
                )
            conn.commit()
        return len(markets)

    def list_open_positions(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, token_id, condition_id, side, size, avg_entry, opened_at
                FROM positions
                WHERE closed_at IS NULL
                ORDER BY opened_at ASC
                """
            )
            return _rows(cur)

    def upsert_position(self, *, token_id: str, condition_id: str, side: str, size: Decimal, avg_entry: Decimal) -> None:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, size, avg_entry FROM positions WHERE token_id = %s AND closed_at IS NULL",
                (token_id,),
            )
            row = cur.fetchone()
            if row:
                old_size = Decimal(str(row["size"]))
                old_avg = Decimal(str(row["avg_entry"]))
                new_size = old_size + size
                new_avg = ((old_size * old_avg) + (size * avg_entry)) / new_size
                cur.execute(
                    "UPDATE positions SET size = %s, avg_entry = %s WHERE id = %s",
                    (float(new_size), float(new_avg), row["id"]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO positions (id, token_id, condition_id, side, size, avg_entry)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (str(uuid4()), token_id, condition_id, side, float(size), float(avg_entry)),
                )
            conn.commit()

    def close_position(self, token_id: str) -> None:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE positions SET closed_at = %s WHERE token_id = %s AND closed_at IS NULL",
                (datetime.now(timezone.utc), token_id),
            )
            conn.commit()

    def insert_order(self, order: dict[str, Any]) -> str:
        order_id = str(uuid4())
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO orders (
                  id, client_order_id, token_id, condition_id, side, price, size,
                  status, clob_order_id, dry_run, error_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    order_id,
                    order["client_order_id"],
                    order["token_id"],
                    order.get("condition_id"),
                    order["side"],
                    float(order["price"]),
                    float(order["size"]),
                    order.get("status", "pending"),
                    order.get("clob_order_id"),
                    int(bool(order.get("dry_run", False))) if self._use_sqlite else order.get("dry_run", False),
                    order.get("error_message"),
                ),
            )
            conn.commit()
        return order_id

    _UPDATE_FIELD_MAP = {
        "status": "status",
        "clob_order_id": "clob_order_id",
        "error_message": "error_message",
        "updated_at": "updated_at",
    }

    def update_order(self, client_order_id: str, **fields: Any) -> None:
        updates = {}
        for k, v in fields.items():
            col = self._UPDATE_FIELD_MAP.get(k)
            if col is not None:
                updates[col] = v
        if not updates:
            return
        updates["updated_at"] = datetime.now(timezone.utc)
        if self._use_sqlite:
            updates["updated_at"] = updates["updated_at"].isoformat()
        sets = ", ".join(f"{col} = %s" for col in updates)
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE orders SET {sets} WHERE client_order_id = %s",
                (*updates.values(), client_order_id),
            )
            conn.commit()

    def order_exists(self, client_order_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM orders WHERE client_order_id = %s", (client_order_id,))
            return cur.fetchone() is not None

    def record_decision(self, decision: dict[str, Any]) -> str:
        decision_id = str(uuid4())
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO agent_decisions (
                  id, run_id, action, token_id, condition_id, price, size, reasoning, model
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    decision_id,
                    decision["run_id"],
                    decision["action"],
                    decision.get("token_id"),
                    decision.get("condition_id"),
                    decision.get("price"),
                    decision.get("size"),
                    sanitize_text(decision.get("reasoning", ""), 1000),
                    decision.get("model", "potato-engine"),
                ),
            )
            conn.commit()
        return decision_id

    def get_risk_state(self, day: date | None = None) -> dict[str, Any]:
        day = day or date.today()
        day_val = day.isoformat() if self._use_sqlite else day
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT day, spent_cny, trade_count, circuit_breaker FROM risk_limits WHERE day = %s",
                (day_val,),
            )
            row = cur.fetchone()
            if not row:
                return {"day": str(day), "spent_cny": "0", "trade_count": 0, "circuit_breaker": False}
            return {
                "day": str(row["day"]),
                "spent_cny": str(row["spent_cny"]),
                "trade_count": int(row["trade_count"]),
                "circuit_breaker": bool(row["circuit_breaker"]),
            }

    def record_spend(self, amount_cny: Decimal) -> dict[str, Any]:
        day = date.today()
        day_val = day.isoformat() if self._use_sqlite else day
        with self.connect() as conn:
            cur = conn.cursor()
            if self._use_sqlite:
                cur.execute("SELECT spent_cny, trade_count FROM risk_limits WHERE day = %s", (day_val,))
                row = cur.fetchone()
                if row:
                    cur.execute(
                        """
                        UPDATE risk_limits
                        SET spent_cny = %s, trade_count = %s, updated_at = %s
                        WHERE day = %s
                        """,
                        (
                            float(Decimal(str(row["spent_cny"])) + amount_cny),
                            int(row["trade_count"]) + 1,
                            datetime.now(timezone.utc).isoformat(),
                            day_val,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO risk_limits (day, spent_cny, trade_count, updated_at)
                        VALUES (%s, %s, 1, %s)
                        """,
                        (day_val, float(amount_cny), datetime.now(timezone.utc).isoformat()),
                    )
            else:
                cur.execute(
                    """
                    INSERT INTO risk_limits (day, spent_cny, trade_count)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (day) DO UPDATE SET
                      spent_cny = risk_limits.spent_cny + EXCLUDED.spent_cny,
                      trade_count = risk_limits.trade_count + 1,
                      updated_at = EXCLUDED.updated_at
                    """,
                    (day_val, float(amount_cny)),
                )
            conn.commit()
        return self.get_risk_state(day)

    def set_circuit_breaker(self, enabled: bool) -> None:
        day = date.today()
        day_val = day.isoformat() if self._use_sqlite else day
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO risk_limits (day, circuit_breaker)
                VALUES (%s, %s)
                ON CONFLICT (day) DO UPDATE SET
                  circuit_breaker = EXCLUDED.circuit_breaker,
                  updated_at = EXCLUDED.updated_at
                """,
                (day_val, enabled),
            )
            conn.commit()

    def recent_failed_orders(self, limit: int = 10) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT status FROM orders ORDER BY created_at DESC LIMIT %s", (limit,))
            rows = _rows(cur)
        failures = 0
        for row in rows:
            if row["status"] in {"failed", "rejected", "error"}:
                failures += 1
            else:
                break
        return failures

    def start_cycle(self, run_id: str) -> None:
        with self.connect() as conn:
            cur = conn.cursor()
            if self._use_sqlite:
                cur.execute("DELETE FROM cycle_runs WHERE run_id = %s", (run_id,))
            else:
                cur.execute(
                    """
                    INSERT INTO cycle_runs (run_id, status)
                    VALUES (%s, %s)
                    ON CONFLICT (run_id) DO UPDATE SET
                      status = EXCLUDED.status,
                      summary = NULL,
                      started_at = now(),
                      finished_at = NULL
                    """,
                    (run_id, "running"),
                )
                conn.commit()
                return
            cur.execute("INSERT INTO cycle_runs (run_id, status) VALUES (%s, %s)", (run_id, "running"))
            conn.commit()

    def finish_cycle(self, run_id: str, status: str, summary: dict[str, Any]) -> None:
        payload = json.dumps(summary, ensure_ascii=False)
        finished = datetime.now(timezone.utc)
        finished_val = finished.isoformat() if self._use_sqlite else finished
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE cycle_runs SET status = %s, summary = %s, finished_at = %s WHERE run_id = %s
                """,
                (status, payload, finished_val, run_id),
            )
            conn.commit()

    def top_markets(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT condition_id, question, token_id_yes, token_id_no,
                       price_yes, price_no, volume_24h, spread_pct
                FROM markets
                WHERE active = 1
                ORDER BY COALESCE(volume_24h, 0) DESC
                LIMIT %s
                """,
                (limit,),
            )
            return _rows(cur)


class _PgConn:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def commit(self):
        self._conn.commit()


class _SQLiteConn:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def cursor(self):
        return _SQLiteCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def executescript(self, script: str):
        self._conn.executescript(script)


class _SQLiteCursor:
    def __init__(self, cur: sqlite3.Cursor):
        self._cur = cur

    def execute(self, query: str, params=None):
        self._cur.execute(query.replace("%s", "?"), params or ())
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self):
        return [dict(r) for r in self._cur.fetchall()]


def _rows(cur) -> list[dict[str, Any]]:
    fetched = cur.fetchall()
    if not fetched:
        return []
    if isinstance(fetched[0], dict):
        return [dict(r) for r in fetched]
    description = getattr(cur, "description", None)
    if not description and hasattr(cur, "_cur"):
        description = cur._cur.description
    cols = [d[0] for d in description] if description else []
    return [dict(zip(cols, row)) for row in fetched]
