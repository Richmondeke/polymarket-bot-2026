"""
End-to-end order placement test.
Uses a real active market with a very low price (near 0) to test safely.
"""
import sys
from bot import config
from py_clob_client_v2 import ClobClient
from py_clob_client_v2.clob_types import OrderArgs, PartialCreateOrderOptions
from py_clob_client_v2.order_builder.constants import BUY

print(f"LIVE_TRADING={config.LIVE_TRADING}, DRY_RUN={config.DRY_RUN}")

# Bootstrap and derive
bootstrap = ClobClient(host=config.CLOB_HOST, chain_id=config.CHAIN_ID, key=config.POLYGON_PRIVATE_KEY)
creds = bootstrap.derive_api_key()
print(f"Derived API key: {creds.api_key}")

client = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
    creds=creds,
)

# Verify auth works
orders = client.get_open_orders()
print(f"Open orders (auth test): {orders}")
print("✅ Authentication working!")

# Find a liquid market to get a valid token_id
import requests
resp = requests.get("https://gamma-api.polymarket.com/markets", params={"active":"true","closed":"false","limit":20,"min_volume":"50000"}, timeout=10)
markets = resp.json() if isinstance(resp.json(), list) else []
print(f"Found {len(markets)} active markets")

# Use a token_id from an active market
token_id = None
question = None
for m in markets:
    try:
        import json
        ids = json.loads(m.get("clobTokenIds","[]"))
        if ids:
            # Get tick_size info
            token_id = ids[0]
            question = m.get("question","")
            break
    except:
        pass

if not token_id:
    print("Could not find market, using hardcoded token for test")
    token_id = "73470541315377973562501025254719659796416871135081220986683321361000395461644"
    question = "Test market"

print(f"\nUsing market: {question[:60]}")
print(f"Token ID: {token_id}")

# Place a very small test order at a very low price (won't fill, just tests API acceptance)
try:
    result = client.create_and_post_order(
        order_args=OrderArgs(token_id=token_id, price=0.01, side=BUY, size=5.0),
        options=PartialCreateOrderOptions(tick_size="0.01"),
    )
    print(f"\n🎉 ORDER PLACED SUCCESSFULLY!")
    print(f"Result: {result}")
except Exception as e:
    print(f"\n❌ Order failed: {e}")
