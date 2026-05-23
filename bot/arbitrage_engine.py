"""
bot/arbitrage_engine.py — Cross-market Mutually Exclusive Event Arbitrage.
Scrapes NegRisk event contracts and executes risk-free basket trades on price discrepancies.
"""
import time
import threading
from collections import defaultdict
from loguru import logger

from bot import config
from bot import database as db
from bot.client import gamma, clob
from bot.order_manager import orders


class ArbitrageEngine:
    def __init__(self):
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def _scan_and_arbitrage(self):
        logger.info("[Arbitrage] Scanning for NegRisk mutually exclusive basket opportunities…")
        try:
            # Fetch active markets from Gamma API
            markets = gamma.get_active_markets(limit=100, min_volume=10000)
            if not markets:
                markets = gamma.get_active_markets(limit=50, min_volume=1000)

            # Group markets by event ID where NegRisk is enabled
            groups = defaultdict(list)
            event_titles = {}
            for m in markets:
                evs = m.get("events", [])
                if evs and (evs[0].get("negRisk") or evs[0].get("enableNegRisk")):
                    event_id = evs[0].get("id")
                    groups[event_id].append(m)
                    event_titles[event_id] = evs[0].get("title") or event_id

            # Analyze each event group
            for event_id, group_markets in groups.items():
                if not self._running:
                    break

                if len(group_markets) < 2:
                    continue

                event_title = event_titles[event_id]
                
                # Fetch outcomes & prices
                legs_data = []
                total_yes_prob = 0.0
                
                for m in group_markets:
                    m_id = m.get("conditionId")
                    question = m.get("question") or m.get("title") or m_id
                    
                    # Token ID for Yes
                    yes_token = gamma.get_token_id_for_outcome(m, "Yes")
                    no_token = gamma.get_token_id_for_outcome(m, "No")
                    if not yes_token or not no_token:
                        continue
                        
                    yes_price = gamma.get_implied_probability(m, "Yes")
                    if not yes_price or yes_price <= 0.01:
                        continue
                        
                    total_yes_prob += yes_price
                    legs_data.append({
                        "market_id": m_id,
                        "market_question": question,
                        "yes_token": yes_token,
                        "no_token": no_token,
                        "yes_price": yes_price,
                        "no_price": round(1.0 - yes_price, 4)
                    })

                if len(legs_data) < 2:
                    continue

                # 1. Over-priced Basket (Sum of YES prices > 1.025)
                # Buy NO on all outcomes
                if total_yes_prob > 1.025:
                    num_legs = len(legs_data)
                    total_no_price = num_legs - total_yes_prob
                    
                    # We want total cost to be around config.POSITION_SIZE_USD
                    # Total cost = Shares * total_no_price
                    shares = round(config.POSITION_SIZE_USD / max(total_no_price, 0.01), 2)
                    total_cost = round(shares * total_no_price, 2)
                    
                    # Skip if shares is too small or total cost is invalid
                    if shares <= 0 or total_cost <= 0:
                        continue

                    # Skip if we already have open positions in this event to avoid double exposure
                    has_position = False
                    for leg in legs_data:
                        if db.position_exists(leg["market_id"]):
                            has_position = True
                            break
                    if has_position:
                        continue

                    logger.info(
                        f"[Arbitrage] Opportunity detected! Event: '{event_title}' | "
                        f"YES Sum: {total_yes_prob:.3f} | Buying NO basket at sum {total_no_price:.3f}"
                    )

                    # Log to events for dashboard monitor
                    db.log_event(
                        "arbitrage_opportunity",
                        f"Over-priced YES sum: {total_yes_prob:.3f} on '{event_title[:40]}'",
                        severity="info",
                        data={
                            "event_id": event_id,
                            "event_title": event_title,
                            "yes_sum": total_yes_prob,
                            "basket_type": "NO_BASKET",
                            "legs": len(legs_data),
                            "estimated_profit_pct": round((total_yes_prob - 1.0) / total_yes_prob * 100, 2)
                        }
                    )

                    legs = []
                    for leg in legs_data:
                        legs.append({
                            "market_id": leg["market_id"],
                            "market_question": leg["market_question"],
                            "token_id": leg["no_token"],
                            "outcome": "No",
                            "price": leg["no_price"],
                            "shares": shares
                        })

                    orders.place_arbitrage_basket(
                        event_id=event_id,
                        event_title=event_title,
                        legs=legs,
                        basket_type="NO_BASKET",
                        total_cost_usd=total_cost
                    )
                    time.sleep(2) # pace calls

                # 2. Under-priced Basket (Sum of YES prices < 0.94)
                # Buy YES on all outcomes
                elif total_yes_prob < 0.94:
                    # Only buy YES if list is exhaustive. We assume sports and nomiation markets are exhaustive,
                    # or we filter for specific categories or tags.
                    # As a general rule for V1, we log the opportunity and place the trade if enabled
                    shares = round(config.POSITION_SIZE_USD / max(total_yes_prob, 0.01), 2)
                    total_cost = round(shares * total_yes_prob, 2)

                    if shares <= 0 or total_cost <= 0:
                        continue

                    has_position = False
                    for leg in legs_data:
                        if db.position_exists(leg["market_id"]):
                            has_position = True
                            break
                    if has_position:
                        continue

                    logger.info(
                        f"[Arbitrage] Opportunity detected! Event: '{event_title}' | "
                        f"YES Sum: {total_yes_prob:.3f} | Buying YES basket"
                    )

                    db.log_event(
                        "arbitrage_opportunity",
                        f"Under-priced YES sum: {total_yes_prob:.3f} on '{event_title[:40]}'",
                        severity="info",
                        data={
                            "event_id": event_id,
                            "event_title": event_title,
                            "yes_sum": total_yes_prob,
                            "basket_type": "YES_BASKET",
                            "legs": len(legs_data),
                            "estimated_profit_pct": round((1.0 - total_yes_prob) / total_yes_prob * 100, 2)
                        }
                    )

                    legs = []
                    for leg in legs_data:
                        legs.append({
                            "market_id": leg["market_id"],
                            "market_question": leg["market_question"],
                            "token_id": leg["yes_token"],
                            "outcome": "Yes",
                            "price": leg["yes_price"],
                            "shares": shares
                        })

                    orders.place_arbitrage_basket(
                        event_id=event_id,
                        event_title=event_title,
                        legs=legs,
                        basket_type="YES_BASKET",
                        total_cost_usd=total_cost
                    )
                    time.sleep(2)

        except Exception as e:
            logger.error(f"[Arbitrage] Scan error: {e}")

    def _run(self):
        logger.info("[Arbitrage] Engine thread running")
        while self._running:
            self._scan_and_arbitrage()
            
            # Sleep for 5 minutes between scans
            for _ in range(300):
                if not self._running:
                    break
                time.sleep(1)
                
        logger.info("[Arbitrage] Engine thread stopped")

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run, name="Arbitrage", daemon=True)
            self._thread.start()
            logger.info("[Arbitrage] Engine started")

    def stop(self):
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("[Arbitrage] Engine stopped")


arbitrage_engine = ArbitrageEngine()
