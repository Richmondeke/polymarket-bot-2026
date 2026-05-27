import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from web3 import Web3

load_dotenv()
host = "https://clob.polymarket.com"
chain_id = 137

client = ClobClient(
    host,
    key=os.getenv("POLYGON_PRIVATE_KEY"),
    chain_id=chain_id
)

w3 = Web3(Web3.HTTPProvider("https://polygon-mainnet.g.alchemy.com/v2/ttJkYMXVkirrBeMz4EKmY"))
proxy_wallet = client.get_address()

print(f"Proxy Wallet: {proxy_wallet}")

abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
usdc_e = w3.eth.contract(address=w3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"), abi=abi)

bal_e = usdc_e.functions.balanceOf(proxy_wallet).call()
print(f"Proxy USDC.e: {bal_e / 1e6}")

bal_n = usdc_n = w3.eth.contract(address=w3.to_checksum_address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"), abi=abi).functions.balanceOf(proxy_wallet).call()
print(f"Proxy Native USDC: {bal_n / 1e6}")
