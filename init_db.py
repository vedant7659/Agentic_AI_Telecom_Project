"""One-time script to initialise data/telecom_ops.db from the provided SQL scripts."""
import sqlite3
import os

DB_PATH = "data/telecom_ops.db"
os.makedirs("data", exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 1. Schema
with open("sql/01_schema.sql", "r") as f:
    cursor.executescript(f.read())
print("[OK] Schema created.")

# 2. Seed data
with open("sql/02_seed_data.sql", "r") as f:
    cursor.executescript(f.read())
print("[OK] Seed data inserted.")

conn.commit()

# 3. Verify
tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
table_names = [t[0] for t in tables]
print(f"\nTables ({len(table_names)}):")
for name in table_names:
    count = cursor.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    print(f"   {name:<30} {count} rows")

conn.close()
print(f"\n[DONE] Database ready: {DB_PATH}")
