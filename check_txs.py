import requests

wallet = "0x8E1af49c1E18fE0351791d5052c9e76200C63081"
url = f"https://api.polygonscan.com/api?module=account&action=tokentx&address={wallet}&page=1&offset=5&sort=desc&apikey=YourApiKeyToken"

response = requests.get(url).json()
for tx in response.get("result", []):
    print(f"Token: {tx['tokenSymbol']} ({tx['contractAddress']}), Value: {int(tx['value'])/10**int(tx['tokenDecimal'])}")
