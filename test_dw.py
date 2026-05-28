import json
from bot import config
from py_clob_client_v2 import ClobClient, ApiCreds
from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
import requests

eoa = "0x8E1af49c1E18fE0351791d5052c9e76200C63081"
dw_addr = "0x71e2a68115542f4CcC394D4953449a0734139F26"

print(f"LIVE_TRADING={config.LIVE_TRADING}, DRY_RUN={config.DRY_RUN}")

# Step 1: Derive API creds
bootstrap = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
)
creds = bootstrap.derive_api_key()
print(f"Derived API key: {creds.api_key}")
print(f"EOA address: {bootstrap.get_address()}")

# Step 2: Create client with POLY_1271 signature type and funder=dw_addr
client = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
    creds=creds,
    signature_type=3,  # POLY_1271
    funder=dw_addr,
)

print(f"\nClient configured with signature_type=3 (POLY_1271)")
print(f"Builder funder: {client.builder.funder}")
print(f"Builder signature_type: {client.builder.signature_type}")

# Step 3: Test auth
orders = client.get_open_orders()
print(f"Open orders (auth test): {orders}")
print("✅ Authentication working!")

# Step 4: Check balance/allowance for the deposit wallet
bal = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
print(f"\nBalance/Allowance (POLY_1271): {bal}")

# Step 5: Find a valid token_id
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
    exit(1)

print(f"Using market: {question[:60]}")
print(f"Token ID: {token_id}")

# Step 6: Place a test order (very low price, won't fill)
from py_clob_client_v2.clob_types import OrderArgs, PartialCreateOrderOptions
from py_clob_client_v2.order_builder.constants import BUY

try:
    result = client.create_and_post_order(
        order_args=OrderArgs(token_id=token_id, price=0.01, side=BUY, size=5.0),
        options=PartialCreateOrderOptions(tick_size="0.01"),
    )
    print(f"\n🎉 ORDER PLACED SUCCESSFULLY!")
    print(f"Result: {result}")
except Exception as e:
    print(f"\n❌ Order failed: {e}")
    import traceback
    traceback.print_exc()
