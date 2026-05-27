from web3 import Web3

w3_base = Web3(Web3.HTTPProvider("https://mainnet.base.org"))
w3_arb = Web3(Web3.HTTPProvider("https://arb1.arbitrum.io/rpc"))
w3_eth = Web3(Web3.HTTPProvider("https://eth.llamarpc.com"))

wallet = Web3.to_checksum_address("0x8E1af49c1E18fE0351791d5052c9e76200C63081")
abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]

base_usdc = w3_base.eth.contract(address=w3_base.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"), abi=abi)
try:
    print(f"Base USDC: {base_usdc.functions.balanceOf(wallet).call() / 1e6}")
except:
    pass

arb_usdc = w3_arb.eth.contract(address=w3_arb.to_checksum_address("0xaf88d065e77c8cC2239327C5EDb3A432268e5831"), abi=abi)
try:
    print(f"Arbitrum USDC: {arb_usdc.functions.balanceOf(wallet).call() / 1e6}")
except:
    pass
    
eth_usdc = w3_eth.eth.contract(address=w3_eth.to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eb48"), abi=abi)
try:
    print(f"Mainnet USDC: {eth_usdc.functions.balanceOf(wallet).call() / 1e6}")
except:
    pass
