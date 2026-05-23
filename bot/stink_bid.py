"""
bot/stink_bid.py — Deep discount limit order strategy.
Periodically scans highly liquid markets (favorites) and places
stink bids (deep discount BUY limit orders) that only fill if a whale dumps.
"""
import threading
import time
from datetime import datetime, timezone
from loguru import logger

from bot import config
from bot.client import gamma, clob
from bot.order_manager import orders
from bot import database as db


class StinkBidEngine:
    def __init__(self):
        self._running = False
        self._thread = None

    def _scan_and_place(self):
        if not config.STINK_BID_ENABLED:
            return

        logger.info("[StinkBid] Scanning for opportunities…")
        try:
            # Clean up old/expired bids
            open_count = orders.get_open_order_count()
            
            # Fetch active markets (e.g., Politics tag)
            # You can make this configurable. Using 'Politics' as default high liquidity
            markets = gamma.get_active_markets(category="Politics", limit=20, min_volume=100000)
            if not markets:
                logger.info("[StinkBid] No high-volume Politics markets found. Relaxing search criteria...")
                markets = gamma.get_active_markets(limit=20, min_volume=1000)
            
            placed_this_round = 0

            for market in markets:
                if placed_this_round >= config.STINK_BID_MAX_OPEN or open_count >= config.STINK_BID_MAX_OPEN:
                    break

                market_id = market.get("conditionId")
                if not market_id:
                    continue

                # Filter by resolution time
                if not config.is_market_fast_resolving(market):
                    continue


                # Get token ID for 'Yes' outcome
                token_id = gamma.get_token_id_for_outcome(market, "Yes")
                if not token_id:
                    continue

                # Check if we already have a position or order here
                if db.position_exists(market_id) or f"stink_{market_id}" in orders._open_order_ids:
                    continue

                # Determine if it's a favorite
                implied_prob = gamma.get_implied_probability(market, "Yes")
                min_prob = 0.10 if config.DRY_RUN else config.STINK_BID_MIN_PROB
                if not implied_prob or implied_prob < min_prob:
                    continue

                # Get live best ask from CLOB
                best_ask = clob.get_best_ask(token_id)
                if not best_ask or best_ask < 0.1:
                    continue

                question = market.get("question") or market.get("title") or market_id
                
                # Place the stink bid!
                resp = orders.place_stink_bid(
                    market_id=market_id,
                    market_question=question,
                    token_id=token_id,
                    best_ask=best_ask,
                    size_usd=config.POSITION_SIZE_USD,
                    discount_pct=config.STINK_BID_DISCOUNT,
                    end_date=market.get("endDate"),
                )
                
                if resp:
                    placed_this_round += 1
                    open_count += 1
                    time.sleep(1) # Pace API calls
                    
        except Exception as e:
            logger.error(f"[StinkBid] Scan error: {e}")

    def _run(self):
        logger.info("[StinkBid] Started")
        while self._running:
            self._scan_and_place()
            
            # Sleep for 10 minutes between scans
            for _ in range(600):
                if not self._running:
                    break
                time.sleep(1)
                
        logger.info("[StinkBid] Stopped")

    def start(self):
        if not config.STINK_BID_ENABLED:
            logger.info("[StinkBid] Disabled in config")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="StinkBid", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)


stink_bid_engine = StinkBidEngine()
