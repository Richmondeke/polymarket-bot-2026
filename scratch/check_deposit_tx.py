from web3 import Web3

# Use standard public Polygon RPC to avoid Alchemy limits if needed, or stick to Alchemy with small block range
rpcs = [
    "https://polygon-rpc.com/",
    "https://polygon-mainnet.g.alchemy.com/v2/ttJkYMXVkirrBeMz4EKmY"
]

for rpc in rpcs:
    try:
        w3 = Web3(Web3.HTTPProvider(rpc))
        if w3.is_connected():
            print(f"Connected to {rpc}")
            eoa = w3.to_checksum_address("0x8E1af49c1E18fE0351791d5052c9e76200C63081")
            deposit_wallet = w3.to_checksum_address("0x71e2a68115542f4CcC394D4953449a0734139F26")
            usdc_n_addr = w3.to_checksum_address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359")

            # ERC20 Transfer event signature: Transfer(address indexed from, address indexed to, uint256 value)
            transfer_event_hash = w3.keccak(text="Transfer(address,address,uint256)").hex()
            topic_from_eoa = "0x" + eoa[2:].lower().zfill(64)
            topic_to_dw = "0x" + deposit_wallet[2:].lower().zfill(64)

            # Let's search the last 15,000 blocks (approx. 8 hours)
            latest_block = w3.eth.block_number
            from_block = latest_block - 15000
            print(f"Searching from block {from_block} to {latest_block}...")
            
            filter_params = {
                "fromBlock": from_block,
                "toBlock": "latest",
                "address": usdc_n_addr,
                "topics": [transfer_event_hash, topic_from_eoa, topic_to_dw]
            }
            logs = w3.eth.get_logs(filter_params)
            for log in logs:
                val = int(log['data'].hex(), 16) / 1e6
                tx_hash = log['transactionHash'].hex()
                block_num = log['blockNumber']
                print(f"FOUND MATCH: Block {block_num} | Tx: {tx_hash} | Transferred {val:.4f} USDC from EOA to Deposit Wallet")
            
            # Also check any general transfers from EOA to anywhere in last 15,000 blocks
            print("\nScanning for ANY USDC Native transfers from EOA in the same block range...")
            filter_params_any = {
                "fromBlock": from_block,
                "toBlock": "latest",
                "address": usdc_n_addr,
                "topics": [transfer_event_hash, topic_from_eoa]
            }
            logs_any = w3.eth.get_logs(filter_params_any)
            for log in logs_any:
                to_addr = w3.to_checksum_address("0x" + log['topics'][2].hex()[-40:])
                val = int(log['data'].hex(), 16) / 1e6
                tx_hash = log['transactionHash'].hex()
                block_num = log['blockNumber']
                print(f"Block {block_num} | Tx: {tx_hash} | Sent {val:.4f} USDC to {to_addr}")
            break
    except Exception as e:
        print(f"Failed with RPC {rpc}: {e}")
