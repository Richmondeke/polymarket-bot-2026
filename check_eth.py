from web3 import Web3

w3 = Web3(Web3.HTTPProvider("https://eth.public-rpc.com"))
wallet = Web3.to_checksum_address("0x8E1af49c1E18fE0351791d5052c9e76200C63081")
abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]

usdc = w3.eth.contract(address=w3.to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eb48"), abi=abi)
print(f"Mainnet USDC: {usdc.functions.balanceOf(wallet).call() / 1e6}")
