import sqlite3
from typing import Any, Iterable

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assets_reference (
  inventory_number TEXT PRIMARY KEY,
  name TEXT,
  accepted_date TEXT,
  owner TEXT,
  serial_number TEXT,
  last_update_date TEXT,
  cabinet TEXT
);

CREATE TABLE IF NOT EXISTS assets_current (
  inventory_number TEXT PRIMARY KEY,
  name TEXT,
  accepted_date TEXT,
  owner TEXT,
  serial_number TEXT,
  last_update_date TEXT,
  cabinet TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS movements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  moved_at TEXT NOT NULL,
  initiator_tg_id INTEGER,
  initiator_username TEXT,
  initiator_name TEXT,
  inventory_number TEXT NOT NULL,
  from_owner TEXT,
  from_cabinet TEXT,
  to_owner TEXT,
  to_cabinet TEXT,
  comment TEXT,
);
"""

def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    """
    Добавляет колонку в существующую таблицу, если её нет.
    Полезно для 'миграций' в SQLite без alembic.
    """
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()

def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)

    # на всякий случай: если таблица movements уже была создана раньше без initiator_name
    _ensure_column(conn, "movements", "initiator_name", "TEXT")

    return conn

def execmany(conn: sqlite3.Connection, sql: str, rows: Iterable[Iterable[Any]]) -> None:
    conn.executemany(sql, rows)
    conn.commit()