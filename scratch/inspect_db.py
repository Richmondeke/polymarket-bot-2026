import sqlite3
import os

db_dir = "/Users/mac/.gemini/antigravity/scratch/polymarket-bot/data"
for f in os.listdir(db_dir):
    if f.endswith(".db"):
        path = os.path.join(db_dir, f)
        print(f"=== DB: {f} ===")
        try:
            conn = sqlite3.connect(path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            print("Tables:", tables)
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  Table '{table}': {count} rows")
                if count > 0:
                    cursor.execute(f"PRAGMA table_info({table})")
                    cols = [col[1] for col in cursor.fetchall()]
                    cursor.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 5")
                    rows = cursor.fetchall()
                    print(f"  Columns: {cols}")
                    print(f"  Last 5 rows:")
                    for r in rows:
                        print("    ", r)
            conn.close()
        except Exception as e:
            print(f"Error reading {f}: {e}")
        print()
