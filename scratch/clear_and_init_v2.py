import asyncio
import os
import sqlite3
from bot import config
from polynode.trading.trader import PolyNodeTrader
from polynode.trading.types import TraderConfig, OrderParams, SignatureType, ExchangeVersion
import requests
import json

async def main():
    db_path = "data/trading.db"
    
    # 1. Clear credentials table from database so it's a clean slate
    print("Clearing credentials from data/trading.db...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clob_credentials")
    conn.commit()
    conn.close()
    print("Cleared successfully.")
    
    eoa_key = config.POLYGON_PRIVATE_KEY
    
    # 2. Configure PolyNodeTrader
    trader_config = TraderConfig(
        polynode_key="",
        db_path=db_path,
        rpc_url=config.POLYGON_RPC_URL,
        cosigner_url="",  # direct to Polymarket CLOB
        exchange_version=ExchangeVersion.V2,
        fallback_direct=True,
    )
    
    trader = PolyNodeTrader(config=trader_config)
    
    # 3. Ensure ready using POLY_1271 (type 3)
    status = await trader.ensure_ready(eoa_key, type=SignatureType.POLY_1271)
    print("\nTrader Status after fresh initialization:")
    print("  Wallet:        ", status.wallet)
    print("  Funder:        ", status.funder_address)
    print("  Signature type:", status.signature_type)
    print("  Safe deployed: ", status.safe_deployed)
    print("  Approvals set: ", status.approvals_set)
    print("  Actions:       ", status.actions)
    
    # Let's inspect the sqlite row that was just saved to verify it's correct
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT wallet_address, funder_address, signature_type FROM clob_credentials")
    row = cursor.fetchone()
    print("\nSaved Database Credentials Row:")
    print("  Wallet Address: ", row[0])
    print("  Funder Address: ", row[1])
    print("  Signature Type: ", row[2])
    conn.close()
    
    # 4. Find a valid active market token_id
    resp = requests.get(
        "https://gamma-api.polymarket.com/markets",
        params={"active": "true", "closed": "false", "limit": 10},
        timeout=10,
    )
    markets = resp.json() if isinstance(resp.json(), list) else []
    token_id = None
    question = None
    for m in markets:
        try:
            ids = json.loads(m.get("clobTokenIds", "[]"))
            if ids:
                token_id = ids[0]
                question = m.get("question", "")
                break
        except:
            pass

    if not token_id:
        print("❌ Could not find a market token_id")
        return

    print(f"\nUsing market: {question[:60]}")
    print(f"Token ID: {token_id}")
    
    # 5. Place a test limit order at $0.01 (won't fill, just to test API acceptance)
    params = OrderParams(
        token_id=token_id,
        price=0.01,
        size=5.0,
        side="BUY",
        type="GTC"
    )
    
    print("\nPlacing test V2 order...")
    res = await trader.order(params)
    print("Order Placement Result:")
    print("  Success: ", res.success)
    print("  Order ID:", res.order_id)
    print("  Status:  ", res.status)
    print("  Error:   ", res.error)

if __name__ == "__main__":
    asyncio.run(main())
