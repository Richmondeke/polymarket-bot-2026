import sqlite3
import os
from bot.database import _conn

print("=== Clearing Simulated/Mock Data from trades.db ===")

db_path = "data/trades.db"
tables = ["trades", "positions", "daily_pnl", "system_events"]

try:
    with _conn() as conn:
        cursor = conn.cursor()
        
        # 1. Clear all rows from the database tables
        for table in tables:
            cursor.execute(f"DELETE FROM {table}")
            print(f"Cleared all rows from table: {table}")
        
        # 2. Reset daily_pnl starting balance to 3.9594 (the actual initial trading balance)
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cursor.execute(
            "INSERT INTO daily_pnl (date, starting_balance, ending_balance, realized_pnl, unrealized_pnl) VALUES (?, ?, NULL, 0.0, 0.0)",
            (today, 3.9594)
        )
        print(f"Seeded fresh daily_pnl starting balance of $3.9594 for today ({today}).")
        
        # 3. Log a clean startup event
        now_str = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO system_events (timestamp, event_type, severity, message) VALUES (?, 'system', 'info', 'Database initialized clean for live V2 trading.')",
            (now_str,)
        )
        
        conn.commit()
    print("Database purged and successfully seeded with actual data!")
    
except Exception as e:
    print("Failed to purge/seed database:", e)
