import requests
import json

wallet = "0x8E1af49c1E18fE0351791d5052c9e76200C63081"
dw = "0x71e2a68115542f4CcC394D4953449a0734139F26"

# Let's try Polygonscan API without the apikey parameter (it often allows rate-limited free calls)
url = f"https://api.polygonscan.com/api?module=account&action=tokentx&address={wallet}&page=1&offset=10&sort=desc"
print("Querying Polygonscan...")
try:
    r = requests.get(url, timeout=10).json()
    print("Status:", r.get("status"), r.get("message"))
    for tx in r.get("result", []):
        print(f"Hash: {tx.get('hash')} | Token: {tx.get('tokenSymbol')} | Val: {int(tx.get('value'))/10**int(tx.get('tokenDecimal'))} | From: {tx.get('from')} | To: {tx.get('to')}")
except Exception as e:
    print("Polygonscan failed:", e)

# Also try Blockscout API (completely free and unauthenticated)
print("\nQuerying Blockscout...")
url_bs = f"https://polygon.blockscout.com/api/v2/addresses/{wallet}/token-transfers?type=ERC-20"
try:
    r = requests.get(url_bs, timeout=10).json()
    items = r.get("items", [])
    for item in items[:5]:
        tx_hash = item.get("tx_hash")
        token = item.get("token", {}).get("symbol")
        val = int(item.get("value", 0)) / 10**int(item.get("token", {}).get("decimals", 18))
        frm = item.get("from", {}).get("hash")
        to = item.get("to", {}).get("hash")
        print(f"Hash: {tx_hash} | Token: {token} | Val: {val:.4f} | From: {frm} | To: {to}")
except Exception as e:
    print("Blockscout failed:", e)
