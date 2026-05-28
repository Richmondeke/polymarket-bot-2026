import sqlite3
from bot import config

db_path = "data/trading.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT wallet_address, funder_address, api_key, api_secret, api_passphrase, signature_type FROM clob_credentials")
row = cursor.fetchone()
conn.close()

print("=== Env Credentials ===")
print("POLY_API_KEY:       ", config.POLY_API_KEY)
print("POLY_API_SECRET:    ", config.POLY_API_SECRET[:10] + "..." if config.POLY_API_SECRET else None)
print("POLY_API_PASSPHRASE:", config.POLY_API_PASSPHRASE[:10] + "..." if config.POLY_API_PASSPHRASE else None)

if row:
    print("\n=== Saved DB Credentials ===")
    print("Wallet:        ", row[0])
    print("Funder:        ", row[1])
    print("API Key:       ", row[2])
    print("API Secret:    ", row[3][:10] + "..." if row[3] else None)
    print("API Passphrase:", row[4][:10] + "..." if row[4] else None)
    print("Signature type:", row[5])
else:
    print("\nNo credentials stored in database.")
