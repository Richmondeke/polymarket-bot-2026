from web3 import Web3

w3_base = Web3(Web3.HTTPProvider("https://mainnet.base.org"))
wallet = Web3.to_checksum_address("0x8E1af49c1E18fE0351791d5052c9e76200C63081")
abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]

base_usdbc = w3_base.eth.contract(address=w3_base.to_checksum_address("0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA"), abi=abi)
print(f"Base USDbC: {base_usdbc.functions.balanceOf(wallet).call() / 1e6}")
