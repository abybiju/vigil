"""Thin raw-sqlite3 data-access layer. No ORM — the schema is tiny and stable.

Marshalling rules (applied at this boundary so the rest of the app sees real Python types):
  bool   <-> INTEGER 0/1
  dict   <-> TEXT (json)
  list   <-> TEXT (json)
  date/datetime -> TEXT ISO-8601
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import config


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encode(value: Any) -> Any:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def get_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else config.DB_PATH
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Idempotently add columns introduced after a DB was first created (cheap migrations)."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    for col, decl in (("platform", "TEXT"), ("external_id", "TEXT")):
        if col not in existing:
            conn.execute(f"ALTER TABLE messages ADD COLUMN {col} {decl}")
    conn.commit()


def init_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Create all tables from the migration. Idempotent (CREATE IF NOT EXISTS + column ensure)."""
    sql = config.MIGRATION_PATH.read_text()
    conn = get_conn(db_path)
    conn.executescript(sql)
    conn.commit()
    _ensure_columns(conn)
    return conn


def insert(conn: sqlite3.Connection, table: str, data: dict[str, Any], *, commit: bool = True) -> None:
    """Insert a row. `table` is an internal constant (never user input)."""
    cols = list(data)
    placeholders = ", ".join("?" for _ in cols)
    vals = [_encode(data[c]) for c in cols]
    conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})", vals)
    if commit:
        conn.commit()


def query(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchall()


def query_one(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, tuple(params)).fetchone()


def audit(conn: sqlite3.Connection, case_id: str | None, actor: str, action: str, detail: dict | None = None) -> None:
    """Append an audit-log entry. `actor` is 'ai' or 'human'."""
    insert(
        conn,
        "audit_log",
        {
            "id": new_id(),
            "case_id": case_id,
            "actor": actor,
            "action": action,
            "detail": detail or {},
            "created_at": now_iso(),
        },
    )
