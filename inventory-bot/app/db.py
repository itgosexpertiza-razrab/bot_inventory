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
  comment TEXT
);

CREATE INDEX IF NOT EXISTS idx_movements_inventory_number_id
  ON movements(inventory_number, id DESC);

CREATE INDEX IF NOT EXISTS idx_assets_current_owner
  ON assets_current(owner);

CREATE INDEX IF NOT EXISTS idx_assets_current_cabinet
  ON assets_current(cabinet);
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


def _recreate_movements_without_fk(conn: sqlite3.Connection) -> None:
    if not conn.execute("PRAGMA foreign_key_list(movements)").fetchall():
        return

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    try:
        conn.execute("DROP TABLE IF EXISTS movements_new")
        conn.execute("""
        CREATE TABLE movements_new (
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
          comment TEXT
        )
        """)
        conn.execute("""
        INSERT INTO movements_new(
          id, moved_at, initiator_tg_id, initiator_username, initiator_name,
          inventory_number, from_owner, from_cabinet, to_owner, to_cabinet, comment
        )
        SELECT
          id, moved_at, initiator_tg_id, initiator_username, COALESCE(initiator_name, ''),
          inventory_number, from_owner, from_cabinet, to_owner, to_cabinet, comment
        FROM movements
        """)
        conn.execute("DROP TABLE movements")
        conn.execute("ALTER TABLE movements_new RENAME TO movements")
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_movements_inventory_number_id
          ON movements(inventory_number, id DESC)
        """)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)

    # на всякий случай: если таблица movements уже была создана раньше без initiator_name
    _ensure_column(conn, "movements", "initiator_name", "TEXT")
    _recreate_movements_without_fk(conn)

    return conn

def execmany(conn: sqlite3.Connection, sql: str, rows: Iterable[Iterable[Any]]) -> None:
    conn.executemany(sql, rows)
    conn.commit()
