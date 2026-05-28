from web3 import Web3
import requests
import json

w3 = Web3(Web3.HTTPProvider("https://polygon-mainnet.g.alchemy.com/v2/ttJkYMXVkirrBeMz4EKmY"))

eoa = w3.to_checksum_address("0x8E1af49c1E18fE0351791d5052c9e76200C63081")
deposit_wallet = w3.to_checksum_address("0x71e2a68115542f4CcC394D4953449a0734139F26")
gnosis_safe = w3.to_checksum_address("0x36B703D32D8C83207212ce582898E2066459e984")

abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]

usdc_n_addr = w3.to_checksum_address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359")
usdc_e_addr = w3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")

usdc_n = w3.eth.contract(address=usdc_n_addr, abi=abi)
usdc_e = w3.eth.contract(address=usdc_e_addr, abi=abi)

print("=== ADDRESS BALANCES ===")
for name, addr in [("EOA", eoa), ("Deposit Wallet", deposit_wallet), ("Gnosis Safe", gnosis_safe)]:
    matic = w3.eth.get_balance(addr) / 1e18
    usdc_native = usdc_n.functions.balanceOf(addr).call() / 1e6
    usdc_bridged = usdc_e.functions.balanceOf(addr).call() / 1e6
    print(f"{name} ({addr}):")
    print(f"  MATIC: {matic:.4f}")
    print(f"  USDC Native: {usdc_native:.4f}")
    print(f"  USDC.e (Bridged): {usdc_bridged:.4f}")
    print()

print("=== RECENT ERC20 TRANSFERS FOR EOA ===")
# Try standard polygonscan public API to list ERC20 token transfers
url = f"https://api.polygonscan.com/api?module=account&action=tokentx&address={eoa}&startblock=0&endblock=99999999&sort=desc&apikey=YourApiKeyToken"
try:
    resp = requests.get(url, timeout=10).json()
    if resp.get("status") == "1":
        txs = resp.get("result", [])[:15]
        for tx in txs:
            from_addr = tx['from']
            to_addr = tx['to']
            val = int(tx['value']) / 10**int(tx['tokenDecimal'])
            symbol = tx['tokenSymbol']
            hash_val = tx['hash']
            print(f"Tx: {hash_val[:10]}... | {symbol} | {val:.4f} | From: {from_addr[:10]}... | To: {to_addr[:10]}...")
    else:
        print("Polygonscan status message:", resp.get("message"))
except Exception as e:
    print("Error querying Polygonscan:", e)

print("\n=== RECENT NATIVE TRANSFERS FOR EOA ===")
url_native = f"https://api.polygonscan.com/api?module=account&action=txlist&address={eoa}&startblock=0&endblock=99999999&sort=desc&apikey=YourApiKeyToken"
try:
    resp = requests.get(url_native, timeout=10).json()
    if resp.get("status") == "1":
        txs = resp.get("result", [])[:15]
        for tx in txs:
            from_addr = tx['from']
            to_addr = tx['to']
            val = int(tx['value']) / 1e18
            hash_val = tx['hash']
            print(f"Tx: {hash_val[:10]}... | MATIC | {val:.4f} | From: {from_addr[:10]}... | To: {to_addr[:10]}...")
    else:
        print("Polygonscan status message:", resp.get("message"))
except Exception as e:
    print("Error querying Polygonscan:", e)
