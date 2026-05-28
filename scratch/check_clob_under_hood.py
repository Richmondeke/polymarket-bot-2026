from py_clob_client_v2 import ClobClient
from bot import config
from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
import requests

bootstrap = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
)
creds = bootstrap.derive_api_key()

eoa = "0x8E1af49c1E18fE0351791d5052c9e76200C63081"
dw = "0x71e2a68115542f4CcC394D4953449a0734139F26"
safe = "0x36B703D32D8C83207212ce582898E2066459e984"

for name, funder in [("EOA", None), ("Explicit EOA", eoa), ("Deposit Wallet", dw), ("Gnosis Safe", safe)]:
    print(f"\n--- Funder: {name} ({funder}) ---")
    try:
        client = ClobClient(
            host=config.CLOB_HOST,
            chain_id=config.CHAIN_ID,
            key=config.POLYGON_PRIVATE_KEY,
            creds=creds,
            signature_type=3,  # POLY_1271
            funder=funder
        )
        bal = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
        print("Balance/Allowance:", bal)
    except Exception as e:
        print("Failed:", e)
