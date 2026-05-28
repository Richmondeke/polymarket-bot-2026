import asyncio
from bot import config
from py_clob_client_v2 import ClobClient, ApiCreds
from py_clob_client_v2.clob_types import OrderArgs, PartialCreateOrderOptions
from py_clob_client_v2.order_builder.constants import BUY
import requests
import json

async def test_placement(signer, maker, signature_type, label):
    print(f"\n=== Testing: {label} ===")
    print(f"  Maker:  {maker}")
    print(f"  Signer: {signer}")
    print(f"  SigType: {signature_type}")
    
    # We derive credentials
    bootstrap = ClobClient(
        host=config.CLOB_HOST,
        chain_id=config.CHAIN_ID,
        key=config.POLYGON_PRIVATE_KEY,
    )
    creds = bootstrap.derive_api_key()
    
    # Create the clob client
    client = ClobClient(
        host=config.CLOB_HOST,
        chain_id=config.CHAIN_ID,
        key=config.POLYGON_PRIVATE_KEY,
        creds=creds,
        signature_type=signature_type,
        funder=maker,
    )
    
    # Find a valid token_id
    resp = requests.get(
        "https://gamma-api.polymarket.com/markets",
        params={"active": "true", "closed": "false", "limit": 10},
        timeout=10,
    )
    markets = resp.json() if isinstance(resp.json(), list) else []
    token_id = None
    for m in markets:
        try:
            ids = json.loads(m.get("clobTokenIds", "[]"))
            if ids:
                token_id = ids[0]
                break
        except:
            pass

    if not token_id:
        print("❌ Could not find a market token_id")
        return

    # In ClobClient, if we want to override the signer address, we can check how ClobClient sets it.
    # In py_clob_client_v2, the signer is usually set by _v2_order_signer or derived from the signature type.
    # Let's try placing order directly using py_clob_client_v2!
    try:
        result = client.create_and_post_order(
            order_args=OrderArgs(token_id=token_id, price=0.01, side=BUY, size=5.0),
            options=PartialCreateOrderOptions(tick_size="0.01"),
        )
        print("🎉 SUCCESS:", result)
    except Exception as e:
        print("❌ FAILED:", e)

# Test both configurations using py_clob_client_v2
async def main():
    eoa = "0x8E1af49c1E18fE0351791d5052c9e76200C63081"
    dw = "0x71e2a68115542f4CcC394D4953449a0734139F26"
    
    # In py_clob_client_v2:
    # 1. With funder=None (defaults to EOA), signature_type=3 (POLY_1271)
    await test_placement(signer=eoa, maker=eoa, signature_type=3, label="Funder=EOA (Default), SignatureType=3")
    
    # 2. With funder=Deposit Wallet, signature_type=3
    await test_placement(signer=dw, maker=dw, signature_type=3, label="Funder=Deposit Wallet, SignatureType=3")

if __name__ == "__main__":
    asyncio.run(main())
