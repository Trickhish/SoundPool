"""One-off migration: add role + speaker/volume/party flags to room_members.

Safe to run multiple times (ADD COLUMN IF NOT EXISTS + idempotent backfill).
"""
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from configuration import config

cdpass = quote_plus(config["database"]["password"])
port = config["database"].get("port", 3306)
engine = create_engine(
    f"mysql+pymysql://{config['database']['user']}:{cdpass}"
    f"@{config['database']['host']}:{port}/{config['database']['name']}")

DDL = [
    "ALTER TABLE room_members ADD COLUMN IF NOT EXISTS role VARCHAR(16) DEFAULT 'guest'",
    "ALTER TABLE room_members ADD COLUMN IF NOT EXISTS can_change_volume TINYINT(1) DEFAULT 0",
    "ALTER TABLE room_members ADD COLUMN IF NOT EXISTS can_manage_speakers TINYINT(1) DEFAULT 0",
    "ALTER TABLE room_members ADD COLUMN IF NOT EXISTS can_manage_party TINYINT(1) DEFAULT 0",
]

BACKFILL = [
    # Existing admins -> 'admin' role (owner corrected below).
    "UPDATE room_members SET role='admin' WHERE is_admin=1",
    # Owner rows -> 'owner'.
    "UPDATE room_members m JOIN rooms r ON m.room_id=r.id AND m.user_id=r.owner_id "
    "SET m.role='owner', m.is_admin=1",
    # Admin/owner get the new capabilities.
    "UPDATE room_members SET can_change_volume=1, can_manage_speakers=1, can_manage_party=1 "
    "WHERE is_admin=1",
]

with engine.begin() as conn:
    for stmt in DDL + BACKFILL:
        conn.execute(text(stmt))
        print("OK:", stmt[:70])

print("Migration complete.")
