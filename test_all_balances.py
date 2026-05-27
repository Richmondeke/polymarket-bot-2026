from web3 import Web3
w3 = Web3(Web3.HTTPProvider("https://polygon-mainnet.g.alchemy.com/v2/ttJkYMXVkirrBeMz4EKmY"))
wallet = w3.to_checksum_address("0x8E1af49c1E18fE0351791d5052c9e76200C63081")

abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]

contracts = {
    "USDC.e": ("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174", 6),
    "USDC Native": ("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", 6),
    "USDT": ("0xc2132D05D31c914a87C6611C10748AEb04B58e8F", 6),
    "WMATIC": ("0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", 18),
}

for name, (addr, dec) in contracts.items():
    c = w3.eth.contract(address=w3.to_checksum_address(addr), abi=abi)
    bal = c.functions.balanceOf(wallet).call()
    print(f"{name}: {bal / 10**dec}")

print(f"MATIC: {w3.eth.get_balance(wallet) / 1e18}")
