from web3 import Web3
w3 = Web3(Web3.HTTPProvider("https://polygon-mainnet.g.alchemy.com/v2/ttJkYMXVkirrBeMz4EKmY"))
wallet = w3.to_checksum_address("0x8E1af49c1E18fE0351791d5052c9e76200C63081")

matic_wei = w3.eth.get_balance(wallet)
print(f"MATIC: {matic_wei / 1e18}")

abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]

usdc_e = w3.eth.contract(address=w3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"), abi=abi)
bal_e = usdc_e.functions.balanceOf(wallet).call()
print(f"USDC.e (Bridged): {bal_e / 1e6}")

usdc_n = w3.eth.contract(address=w3.to_checksum_address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"), abi=abi)
bal_n = usdc_n.functions.balanceOf(wallet).call()
print(f"USDC (Native): {bal_n / 1e6}")
