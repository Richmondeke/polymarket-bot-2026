import sqlite3
import json

conn = sqlite3.connect("data/trades.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("--- RECENT TRADES ---")
cur.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10")
for row in cur.fetchall():
    print(dict(row))

print("\n--- OPEN POSITIONS ---")
cur.execute("SELECT * FROM positions WHERE is_open = 1")
for row in cur.fetchall():
    print(dict(row))

conn.close()
