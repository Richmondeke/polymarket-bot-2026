from py_clob_client_v2 import ClobClient
from bot import config
import requests
import json

bootstrap = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
)
creds = bootstrap.derive_api_key()

client = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
    creds=creds,
    signature_type=3,
    funder="0x71e2a68115542f4CcC394D4953449a0734139F26",
)

# Fetch user positions from the Data API
print("=== Real-time Polymarket Open Positions ===")
url = f"https://data-api.polymarket.com/positions?user=0x71e2a68115542f4CcC394D4953449a0734139F26"
try:
    resp = requests.get(url, timeout=10)
    if resp.status_code == 200:
        positions = resp.json()
        print("Positions raw count:", len(positions))
        for pos in positions:
            print(f"- Asset: {pos.get('title')}")
            print(f"  Outcome: {pos.get('outcome')}")
            print(f"  Size: {pos.get('size')} shares")
            print(f"  Avg Entry Price: ${float(pos.get('avgPrice', 0)):.4f}")
            print(f"  Current Value: ${float(pos.get('currentValue', 0)):.4f}")
            print(f"  Unrealized P&L: ${float(pos.get('unrealizedPnl', 0)):.4f}")
            print()
    else:
        print("Failed to fetch positions from Data API:", resp.status_code, resp.text)
except Exception as e:
    print("Error:", e)
