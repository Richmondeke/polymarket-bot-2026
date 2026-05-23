"""
scripts/setup_db.py
Creates the SQLite database and all tables if they don't exist.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from bot.database import init_db

if __name__ == "__main__":
    print("Initializing Polymarket Bot Database...")
    init_db()
    print("Done!")
