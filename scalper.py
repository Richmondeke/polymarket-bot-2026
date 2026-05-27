"""
scalper.py — High-frequency scalping engine for Polymarket.
Runs continuously to provide liquidity and scalp tight spreads.
Hedges an initial amount and aims for rapid compounding.
"""
import time
import requests
from loguru import logger
from bot import config
from bot.client import clob
from bot.order_manager import OrderManager

om = OrderManager()

# Scalping Parameters
SCALP_AMOUNT_USD = 100.0
TARGET_SPREAD_CENTS = 2.0  # E.g. bid at 0.50, ask at 0.52
POLL_INTERVAL_SECONDS = 1.5

def get_volatile_markets():
    """Fetch high-volume, soon-to-resolve markets from Gamma API."""
    try:
        r = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={
                "limit": 20,
                "active": "true",
                "closed": "false",
                "order": "volumeNum",
                "ascending": "false"
            },
            timeout=5
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.error(f"[Scalper] Error fetching markets: {e}")
    return []

def get_market_book(token_id: str):
    """Fetch the order book for a specific token."""
    try:
        return clob.client.get_order_book(token_id)
    except Exception as e:
        logger.error(f"[Scalper] Error getting order book: {e}")
        return None

def scalp_loop():
    logger.info("=" * 55)
    logger.info("⚡ Polymarket Scalping Engine Started ⚡")
    logger.info(f"Targeting {TARGET_SPREAD_CENTS}c spreads with ${SCALP_AMOUNT_USD} size.")
    logger.info("=" * 55)
    
    balance = clob.get_usdc_balance()
    logger.info(f"[Scalper] Starting Balance: ${balance:.2f}")
    
    if balance < SCALP_AMOUNT_USD and not config.DRY_RUN:
        logger.warning(f"[Scalper] Insufficient balance for ${SCALP_AMOUNT_USD} scalp size.")
        
    while True:
        markets = get_volatile_markets()
        if not markets:
            time.sleep(5)
            continue
            
        for m in markets[:3]: # Target top 3 volume markets
            tokens = m.get("tokens", [])
            if not tokens: continue
            
            yes_token = tokens[0].get("token_id")
            if not yes_token: continue
            
            book = get_market_book(yes_token)
            if not book: continue
            
            bids = book.bids
            asks = book.asks
            if not bids or not asks: continue
            
            best_bid = float(bids[0].price)
            best_ask = float(asks[0].price)
            spread = (best_ask - best_bid) * 100
            
            logger.debug(f"[Scalper] {m.get('question')} | Bid: {best_bid:.3f} | Ask: {best_ask:.3f} | Spread: {spread:.1f}c")
            
            # If spread is tight and within our target, attempt to place market-making limit orders
            if spread >= TARGET_SPREAD_CENTS and spread <= 5.0:
                logger.info(f"⚡ Scalping Opportunity Found: {m.get('question')}")
                
                my_bid = round(best_bid + 0.001, 3)
                my_ask = round(best_ask - 0.001, 3)
                
                size = round(SCALP_AMOUNT_USD / best_bid, 2)
                
                logger.info(f"   -> Placing Bid at {my_bid} for {size} shares")
                logger.info(f"   -> Placing Ask at {my_ask} for {size} shares")
                
                if not config.DRY_RUN:
                    # Execute live
                    try:
                        # Dummy place order since OrderManager doesn't have generic place_order
                        logger.warning(f"Live trading logic requires clob.client.create_and_post_order for {yes_token}")
                    except Exception as e:
                        logger.error(f"[Scalper] Failed to place order: {e}")
                        
                # We break after one opportunity to let the book settle
                break
                
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    from bot import config
    config.validate()
    try:
        scalp_loop()
    except KeyboardInterrupt:
        logger.info("[Scalper] Stopped by user.")
