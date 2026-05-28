import sys
import os
import requests
import json

# Ensure parent directory is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.client import clob
from bot import config

# Set LIVE_TRADING to True and DRY_RUN to False for testing (since place_limit_order will place a direct $0.01 limit order)
config.LIVE_TRADING = True
config.DRY_RUN = False

print("=== Checking Balance via ClobWrapper ===")
bal = clob.get_usdc_balance()
print(f"Wrapper reported balance: ${bal:.4f}")

# Find active market token_id
print("\n=== Fetching Active Market ===")
resp = requests.get(
    "https://gamma-api.polymarket.com/markets",
    params={"active": "true", "closed": "false", "limit": 10},
    timeout=10,
)
markets = resp.json() if isinstance(resp.json(), list) else []
token_id = None
question = None
for m in markets:
    try:
        ids = json.loads(m.get("clobTokenIds", "[]"))
        if ids:
            token_id = ids[0]
            question = m.get("question", "")
            break
    except:
        pass

if not token_id:
    print("❌ Could not find a market token_id")
    sys.exit(1)

print(f"Using market: {question[:60]}")
print(f"Token ID: {token_id}")

print("\n=== Placing Test Order via ClobWrapper ===")
res = clob.place_limit_order(
    token_id=token_id,
    side="BUY",
    price=0.01,
    size_shares=5.0,
    tick_size="0.01"
)
print("Order result:", res)
