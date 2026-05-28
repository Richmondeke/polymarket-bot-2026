import asyncio
from bot import config
from polynode.trading.trader import PolyNodeTrader
from polynode.trading.types import TraderConfig, OrderParams, SignatureType, ExchangeVersion
import requests
import json

async def main():
    eoa_key = config.POLYGON_PRIVATE_KEY
    
    # Configure PolyNodeTrader with SignatureType.POLY_1271
    trader_config = TraderConfig(
        polynode_key="",
        db_path="data/trading.db",
        rpc_url=config.POLYGON_RPC_URL,
        cosigner_url="",  # direct to Polymarket CLOB
        exchange_version=ExchangeVersion.V2,
        fallback_direct=True,
    )
    
    trader = PolyNodeTrader(config=trader_config)
    
    # Ensure ready using POLY_1271 (signature_type 3)
    status = await trader.ensure_ready(eoa_key, type=SignatureType.POLY_1271)
    print("\nTrader Status:")
    print("  Wallet:        ", status.wallet)
    print("  Funder:        ", status.funder_address)
    print("  Signature type:", status.signature_type)
    print("  Safe deployed: ", status.safe_deployed)
    print("  Approvals set: ", status.approvals_set)
    print("  Actions:       ", status.actions)
    
    # Find a valid token_id
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
    
    # Place a test limit order at $0.01
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
