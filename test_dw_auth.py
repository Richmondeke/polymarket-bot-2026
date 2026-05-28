import time
import requests
from eth_account import Account
from eth_account.messages import encode_typed_data
from py_clob_client_v2 import ClobClient
from bot import config

eoa_key = config.POLYGON_PRIVATE_KEY
eoa_account = Account.from_key(eoa_key)
dw_addr = "0x71e2a68115542f4CcC394D4953449a0734139F26"

print("EOA:", eoa_account.address)
print("DW Address:", dw_addr)

# Build EIP-712 auth message
timestamp = str(int(time.time()))
nonce = 0
CHAIN_ID = 137

# We sign with EOA, but the address inside the message is the DW Address!
# Or is the address inside the message the EOA address?
# Let's try BOTH! First, address inside message is DW Address.
payload = {
    "domain": {
        "name": "ClobAuthDomain",
        "version": "1",
        "chainId": CHAIN_ID,
    },
    "types": {
        "ClobAuth": [
            {"name": "address", "type": "address"},
            {"name": "timestamp", "type": "string"},
            {"name": "nonce", "type": "uint256"},
            {"name": "message", "type": "string"},
        ],
    },
    "primaryType": "ClobAuth",
    "message": {
        "address": dw_addr,  # Try DW address in message
        "timestamp": timestamp,
        "nonce": nonce,
        "message": "This message attests that I control the given wallet",
    },
}

# Sign typed data
signable_message = encode_typed_data(
    domain_data=payload["domain"],
    message_types={"ClobAuth": payload["types"]["ClobAuth"]},
    message_data=payload["message"]
)
signed = eoa_account.sign_message(signable_message)
signature = signed.signature.hex()
if not signature.startswith("0x"):
    signature = "0x" + signature

headers = {
    "POLY_ADDRESS": dw_addr,  # Send DW address as POLY_ADDRESS
    "POLY_SIGNATURE": signature,
    "POLY_TIMESTAMP": timestamp,
    "POLY_NONCE": str(nonce),
    "Accept": "*/*",
    "Content-Type": "application/json"
}

print("\n--- Testing Auth with DW address inside EIP-712 ---")
resp = requests.get(f"{config.CLOB_HOST}/auth/derive-api-key", headers=headers)
print("Derive API key response status:", resp.status_code)
print("Response:", resp.text)

if resp.status_code != 200:
    # Try with EOA address inside EIP-712, but DW address as POLY_ADDRESS header
    payload["message"]["address"] = eoa_account.address
    signable_message = encode_typed_data(
        domain_data=payload["domain"],
        message_types={"ClobAuth": payload["types"]["ClobAuth"]},
        message_data=payload["message"]
    )
    signed = eoa_account.sign_message(signable_message)
    signature = signed.signature.hex()
    if not signature.startswith("0x"):
        signature = "0x" + signature
        
    headers["POLY_SIGNATURE"] = signature
    print("\n--- Testing Auth with EOA address inside EIP-712, but DW as POLY_ADDRESS ---")
    resp = requests.get(f"{config.CLOB_HOST}/auth/derive-api-key", headers=headers)
    print("Derive API key response status:", resp.status_code)
    print("Response:", resp.text)
