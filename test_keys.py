import os
from bot import config
from py_clob_client_v2 import ClobClient

client = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
)
print("Deriving API key...")
creds = client.derive_api_key()
print("Derived EOA Key:", creds.api_key)

client = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
    creds=creds,
)
try:
    print('Orders:', client.get_open_orders())
except Exception as e:
    print(e)
