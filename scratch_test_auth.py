from py_clob_client_v2.client import ClobClient
from py_clob_client_v2.clob_types import ApiCreds
from bot import config

client = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
    signature_type=2,
    funder=config.POLYGON_WALLET_ADDRESS
)
derived = client.create_or_derive_api_key()
print("Derived API Key:", derived)

client = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
    creds=derived,
    signature_type=2,
    funder=config.POLYGON_WALLET_ADDRESS
)
ok = client.get_ok()
print("get_ok():", ok)
