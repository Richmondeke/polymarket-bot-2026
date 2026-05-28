import sys
from py_clob_client_v2.client import ClobClient
from py_clob_client_v2.clob_types import OrderArgs
from bot import config

sig_type = int(sys.argv[1]) if len(sys.argv) > 1 else 1

client = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
    signature_type=sig_type,
    funder=config.POLYGON_WALLET_ADDRESS
)
creds = client.create_or_derive_api_key()
client = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
    creds=creds,
    signature_type=sig_type,
    funder=config.POLYGON_WALLET_ADDRESS
)

try:
    args = OrderArgs(
        price=0.01,
        size=5.0,
        side="BUY",
        token_id="28182404005967940652495463228537840901055649726248190462854914416579180110833"
    )
    res = client.create_and_post_order(args)
    print("SUCCESS with sig type", sig_type)
    print(res)
except Exception as e:
    print("FAILED with sig type", sig_type)
    print(e)
