import requests
import json

url = "https://gamma-api.polymarket.com/markets"
params = {
    "active": "true",
    "closed": "false",
    "limit": 15,
    "min_volume": 50000
}

try:
    resp = requests.get(url, params=params, timeout=10)
    markets = resp.json() if isinstance(resp.json(), list) else []
    print(f"Found {len(markets)} active high-volume markets:")
    for m in markets:
        question = m.get("question")
        slug = m.get("slug")
        prices = m.get("outcomePrices")
        if prices:
            try:
                prices_list = json.loads(prices)
            except:
                prices_list = json.loads(prices.replace("'", "\""))
            yes_price = float(prices_list[0]) if len(prices_list) > 0 else 0.0
            print(f"- Question: {question}")
            print(f"  YES Price: ${yes_price:.2f} | NO Price: ${1.0 - yes_price:.2f}")
            print(f"  Slug: {slug}")
            print()
except Exception as e:
    print("Error fetching markets:", e)
