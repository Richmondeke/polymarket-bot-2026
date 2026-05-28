from py_clob_client_v2 import ClobClient
from bot import config
import requests

bootstrap = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
)
creds = bootstrap.derive_api_key()

# Authenticated CLOB client to fetch profile / account data
# Try EOA first
client = ClobClient(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
    creds=creds,
)

print("=== User Profile from CLOB ===")
try:
    # Query userData or similar from the client
    # Let's inspect the clob client endpoints
    # client has get_ok(), get_api_key_details()
    # Standard endpoint: GET /data/profile or similar or client.get_api_key_details()
    details = client.get_api_key_details()
    print("API Key Details:", details)
except Exception as e:
    print("Failed to get API key details:", e)

# Also fetch the user profile directly from Gamma API using their EOA address
print("\n=== Fetching from Gamma API ===")
url = f"https://gamma-api.polymarket.com/users/{config.POLYGON_WALLET_ADDRESS}"
try:
    resp = requests.get(url, timeout=10)
    print("Response Status:", resp.status_code)
    if resp.status_code == 200:
        print("Gamma Profile:", json.dumps(resp.json(), indent=2))
    else:
        print("Gamma Profile Response:", resp.text)
except Exception as e:
    print("Gamma query failed:", e)

# Try fetching via proxy / profile endpoint
url_profile = f"https://data-api.polymarket.com/profile?address={config.POLYGON_WALLET_ADDRESS}"
try:
    resp = requests.get(url_profile, timeout=10)
    print("\nData API Profile Status:", resp.status_code)
    if resp.status_code == 200:
        print("Data API Profile:", resp.json())
    else:
        print("Data API Profile Response:", resp.text)
except Exception as e:
    print("Data API Profile query failed:", e)
