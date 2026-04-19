"""SQLite database connection and schema management for BuddyAgent."""

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "buddy.db"

_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS notes (
        id         TEXT PRIMARY KEY,
        title      TEXT NOT NULL,
        content    TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS activity_events (
        id              TEXT PRIMARY KEY,
        title           TEXT NOT NULL,
        start_at        TEXT NOT NULL,
        end_at          TEXT NOT NULL,
        location        TEXT NOT NULL DEFAULT '',
        notes           TEXT NOT NULL DEFAULT '',
        recurrence      TEXT NOT NULL DEFAULT 'none',
        recurrence_days TEXT NOT NULL DEFAULT '',
        source          TEXT NOT NULL DEFAULT 'local',
        external_id     TEXT NOT NULL DEFAULT '',
        calendar_name   TEXT NOT NULL DEFAULT '',
        created_at      TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reminders (
        id              TEXT PRIMARY KEY,
        title           TEXT NOT NULL,
        start_at        TEXT NOT NULL,
        end_at          TEXT NOT NULL,
        notes           TEXT NOT NULL DEFAULT '',
        recurrence      TEXT NOT NULL DEFAULT 'none',
        recurrence_days TEXT NOT NULL DEFAULT '',
        created_at      TEXT NOT NULL
    )
    """,
]


def get_db_path() -> Path:
    raw = os.getenv("BUDDY_DB", "").strip()
    path = Path(raw).expanduser() if raw else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    """Return a connection with all schemas guaranteed to exist."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    for stmt in _DDL_STATEMENTS:
        conn.execute(stmt)
    conn.commit()
    return conn
