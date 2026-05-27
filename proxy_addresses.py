import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

load_dotenv()
host = "https://clob.polymarket.com"
chain_id = 137

client = ClobClient(
    host,
    key=os.getenv("POLYGON_PRIVATE_KEY"),
    chain_id=chain_id
)

print(f"Address: {client.get_address()}")
print(f"Collateral: {client.get_collateral_address()}")
print(f"Exchange: {client.get_exchange_address()}")
print(f"Balance Allowance: {client.get_balance_allowance(client.get_collateral_address())}")
