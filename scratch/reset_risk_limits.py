import sqlite3
from bot.database import _conn

print("=== Resetting Risk Manager Daily Balance Peak ===")
try:
    with _conn() as conn:
        cursor = conn.cursor()
        
        # 1. Update daily_pnl table starting_balance to 3.9594
        cursor.execute("UPDATE daily_pnl SET starting_balance = 3.9594, ending_balance = NULL, realized_pnl = 0.0, unrealized_pnl = 0.0")
        print("Updated daily_pnl row(s):", cursor.rowcount)
        
        # 2. Verify daily_pnl contents
        cursor.execute("SELECT * FROM daily_pnl")
        rows = cursor.fetchall()
        print("Current daily_pnl rows:")
        for r in rows:
            print("  ", list(r))
            
except Exception as e:
    print("Failed to reset:", e)
