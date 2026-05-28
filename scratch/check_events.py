from web3 import Web3

w3 = Web3(Web3.HTTPProvider("https://polygon-mainnet.g.alchemy.com/v2/ttJkYMXVkirrBeMz4EKmY"))

eoa = w3.to_checksum_address("0x8E1af49c1E18fE0351791d5052c9e76200C63081")
deposit_wallet = w3.to_checksum_address("0x71e2a68115542f4CcC394D4953449a0734139F26")
usdc_n_addr = w3.to_checksum_address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359")

# ERC20 Transfer event signature: Transfer(address indexed from, address indexed to, uint256 value)
transfer_event_hash = w3.keccak(text="Transfer(address,address,uint256)").hex()

# Topics to search: Transfer from EOA or to Deposit Wallet
# 1. From EOA
topic_from_eoa = "0x" + eoa[2:].lower().zfill(64)
# 2. To Deposit Wallet
topic_to_dw = "0x" + deposit_wallet[2:].lower().zfill(64)

print("=== Transfer logs from EOA ===")
filter_params = {
    "fromBlock": w3.eth.block_number - 50000, # check last ~50k blocks (~1-2 days)
    "toBlock": "latest",
    "address": usdc_n_addr,
    "topics": [transfer_event_hash, topic_from_eoa]
}
logs = w3.eth.get_logs(filter_params)
for log in logs:
    to_addr = w3.to_checksum_address("0x" + log['topics'][2].hex()[-40:])
    val = int(log['data'].hex(), 16) / 1e6
    tx_hash = log['transactionHash'].hex()
    print(f"Tx: {tx_hash} | Sent {val:.4f} USDC to {to_addr}")

print("\n=== Transfer logs to Deposit Wallet ===")
filter_params_dw = {
    "fromBlock": w3.eth.block_number - 50000,
    "toBlock": "latest",
    "address": usdc_n_addr,
    "topics": [transfer_event_hash, None, topic_to_dw]
}
logs_dw = w3.eth.get_logs(filter_params_dw)
for log in logs_dw:
    from_addr = w3.to_checksum_address("0x" + log['topics'][1].hex()[-40:])
    val = int(log['data'].hex(), 16) / 1e6
    tx_hash = log['transactionHash'].hex()
    print(f"Tx: {tx_hash} | Received {val:.4f} USDC from {from_addr}")
