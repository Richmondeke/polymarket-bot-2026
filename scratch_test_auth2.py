from py_clob_client_v2.client import ClobClient
from bot import config

client1 = ClobClient(host=config.CLOB_HOST, chain_id=config.CHAIN_ID, key=config.POLYGON_PRIVATE_KEY, signature_type=1, funder=config.POLYGON_WALLET_ADDRESS)
derived1 = client1.create_or_derive_api_key()
c1 = ClobClient(host=config.CLOB_HOST, chain_id=config.CHAIN_ID, key=config.POLYGON_PRIVATE_KEY, creds=derived1, signature_type=1, funder=config.POLYGON_WALLET_ADDRESS)
print("Type 1:", c1.get_ok())

client2 = ClobClient(host=config.CLOB_HOST, chain_id=config.CHAIN_ID, key=config.POLYGON_PRIVATE_KEY, signature_type=2, funder=config.POLYGON_WALLET_ADDRESS)
derived2 = client2.create_or_derive_api_key()
c2 = ClobClient(host=config.CLOB_HOST, chain_id=config.CHAIN_ID, key=config.POLYGON_PRIVATE_KEY, creds=derived2, signature_type=2, funder=config.POLYGON_WALLET_ADDRESS)
print("Type 2:", c2.get_ok())
