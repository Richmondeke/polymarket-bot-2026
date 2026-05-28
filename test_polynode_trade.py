import asyncio
from bot import config
from polynode import PolyNode
from polynode.trading.trader import PolyNodeTrader
from polynode.trading.types import TraderConfig, OrderParams, SignatureType, ExchangeVersion
from polynode.trading.onboarding import detect_wallet_type
import requests
import json

async def main():
    eoa_key = config.POLYGON_PRIVATE_KEY
    eoa_addr = "0x8E1af49c1E18fE0351791d5052c9e76200C63081"
    
    # 1. Force deposit wallet type and funder
    sig_type = SignatureType.POLY_1271
    funder = "0x71e2a68115542f4CcC394D4953449a0734139F26"
    print("Forced signature type:", sig_type)
    print("Deposit wallet address:", funder)
    
    # 2. Configure PolyNodeTrader
    trader_config = TraderConfig(
        polynode_key="",
        db_path="data/trading.db",
        rpc_url=config.POLYGON_RPC_URL,
        cosigner_url="",  # Bypass cosigner proxy and go direct to CLOB
        exchange_version=ExchangeVersion.V2,
        fallback_direct=True,  # Submit order directly to CLOB
    )
    
    trader = PolyNodeTrader(config=trader_config)
    
    # 3. Ensure ready / onboard
    status = await trader.ensure_ready(eoa_key, type=sig_type)
    print("\nTrader Status:")
    print("  Wallet:        ", status.wallet)
    print("  Funder:        ", status.funder_address)
    print("  Signature type:", status.signature_type)
    print("  Safe deployed: ", status.safe_deployed)
    print("  Approvals set: ", status.approvals_set)
    print("  Actions:       ", status.actions)
    
    # 4. Get active market token_id
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
    
    # 5. Place test limit order at $0.01
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
