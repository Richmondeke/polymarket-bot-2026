"""
bot/cross_line_arb.py — Cross-Line Arbitrage Engine
Scans connected sports markets (e.g., Moneyline vs Spread) on Polymarket.
Looks for mispricing or lag between the connected lines and executes a limit order.
"""
import time
import threading
from typing import List, Dict
from loguru import logger

from bot.client import gamma, clob
from bot.order_manager import orders
from bot import config

class CrossLineArbEngine:
    """
    Identifies related markets within the same sporting event.
    Detects if one market's probability implies an arbitrage opportunity in another.
    """
    def __init__(self):
        self._running = False
        self._thread = None
        self._poll_interval = 60  # Scan every 60s

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, name="CrossLineArb", daemon=True)
        self._thread.start()
        logger.info("[CrossLineArb] Engine started")

    def stop(self):
        self._running = False
        logger.info("[CrossLineArb] Engine stopped")

    def _scan_loop(self):
        while self._running:
            try:
                self._scan_sports_events()
            except Exception as e:
                logger.error(f"[CrossLineArb] Scan error: {e}")
            time.sleep(self._poll_interval)

    def _scan_sports_events(self):
        """Finds events with multiple connected markets (Sports)."""
        events = gamma.get_events(category="Sports", limit=20)
        for event in events:
            if not self._running:
                break
            
            markets = event.get("markets", [])
            # We need events with multiple markets (Moneyline, Spread, Totals)
            if len(markets) < 2:
                continue 
            
            self._analyze_event_markets(event.get("id"), event.get("title", ""), markets)
            time.sleep(2)  # Rate limiting

    def _analyze_event_markets(self, event_id: str, title: str, markets: List[Dict]):
        """
        Compare probabilities across related markets.
        For example: 
        If Market A: "Will Team X win?" (Moneyline) is trading at 60c.
        And Market B: "Will Team X win by 5+ points?" (Spread) is trading at 65c.
        This is a structural mispricing. The spread outcome is a subset of the moneyline outcome, 
        so Spread Prob CANNOT be > Moneyline Prob.
        """
        # Map markets by their questions to find relationships
        moneyline_markets = []
        spread_markets = []
        
        for m in markets:
            if not m.get("active"):
                continue
            q = m.get("question", "").lower()
            if "win the match" in q or "win the game" in q:
                moneyline_markets.append(m)
            elif "spread" in q or "win by" in q:
                spread_markets.append(m)

        # Simplified V1 Logic: Look for structural impossibility between subset outcomes
        for ml_market in moneyline_markets:
            ml_prob = gamma.get_implied_probability(ml_market, "Yes")
            if not ml_prob: continue

            for sp_market in spread_markets:
                sp_prob = gamma.get_implied_probability(sp_market, "Yes")
                if not sp_prob: continue

                # The core Microstructure Arbitrage logic:
                # If a subset condition (Spread) costs MORE than the superset condition (Moneyline),
                # the spread market is lagging or incorrectly repriced by retail.
                # E.g. Buy Moneyline Yes, Sell Spread Yes (or just buy Moneyline Yes as it's underpriced)
                if sp_prob > (ml_prob + 0.05):  # 5% threshold
                    logger.info(f"[CrossLineArb] Structural mispricing found in '{title}'!")
                    logger.info(f"  -> Superset (ML): {ml_market['question']} @ {ml_prob}")
                    logger.info(f"  -> Subset (Spread): {sp_market['question']} @ {sp_prob}")
                    
                    token_id = gamma.get_token_id_for_outcome(ml_market, "Yes")
                    if token_id:
                        orders.place_strategic_limit_order(
                            market_id=ml_market["conditionId"],
                            market_question=ml_market["question"],
                            token_id=token_id,
                            side="BUY",
                            price=ml_prob,
                            size_usd=config.POSITION_SIZE_USD,
                            strategy="cross_line_arb",
                            post_only=True,
                            notes=f"ML prob ({ml_prob}) < Spread prob ({sp_prob})"
                        )

cross_line_engine = CrossLineArbEngine()
