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

# Create clients for all signature types to see which ones are recognized or return something
for sig_type in [0, 1, 2, 3]:
    print(f"\n--- Signature Type {sig_type} ---")
    try:
        client = ClobClient(
            host=config.CLOB_HOST,
            chain_id=config.CHAIN_ID,
            key=config.POLYGON_PRIVATE_KEY,
            creds=creds,
            signature_type=sig_type
        )
        print("Funder:", client.builder.funder)
        from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
        bal = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
        print("Balance/Allowance:", bal)
    except Exception as e:
        print("Failed:", e)
