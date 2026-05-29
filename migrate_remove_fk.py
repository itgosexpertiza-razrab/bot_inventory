import sqlite3
from pathlib import Path

DB = Path("/home/user01/inventoty_bot/data/inventory.sqlite3")

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

conn.execute("PRAGMA foreign_keys=OFF;")
conn.execute("BEGIN;")

conn.execute("""
CREATE TABLE IF NOT EXISTS movements_new (
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
""")

conn.execute("""
INSERT INTO movements_new(
  id, moved_at, initiator_tg_id, initiator_username, initiator_name,
  inventory_number, from_owner, from_cabinet, to_owner, to_cabinet, comment
)
SELECT
  id, moved_at, initiator_tg_id, initiator_username,
  COALESCE(initiator_name,''),
  inventory_number, from_owner, from_cabinet, to_owner, to_cabinet, comment
FROM movements;
""")

conn.execute("DROP TABLE movements;")
conn.execute("ALTER TABLE movements_new RENAME TO movements;")

conn.execute("COMMIT;")
conn.execute("PRAGMA foreign_keys=ON;")

print("OK: movements recreated without FK")
conn.close()
