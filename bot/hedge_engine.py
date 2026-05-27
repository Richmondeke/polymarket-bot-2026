import time
import threading
from typing import List, Dict
from loguru import logger

from bot import config
import bot.database as db
from bot.order_manager import orders

class HedgeEngine:
    """
    Phase 4: Directional Trading + Hedge & Sell-Early Engine
    1. Sell Early: Scans open positions, and if they hit a profit target, submits a limit sell order to exit before the event concludes.
    2. Hedge: If a position is moving against us, submit a counter-position on a correlated market to reduce risk.
    """
    def __init__(self):
        self._running = False
        self._thread = None
        self.take_profit_threshold = 0.15  # Sell if price increases by 15 cents
        self.stop_loss_threshold = 0.10    # Hedge if price drops by 10 cents

    def _simulate_current_price(self, entry_price: float) -> float:
        """
        Mock function to simulate market price movements.
        In production, this would fetch the live orderbook best bid/ask.
        """
        # For simulation, we artificially bump up older positions so we can see the "sell early" logic trigger.
        # We will add 0.20 to the entry price if the price is low, so it hits our take profit threshold.
        if entry_price < 0.80:
            return entry_price + 0.20
        return entry_price - 0.15 # simulate a drop for stop loss

    def scan_open_positions(self):
        """Main loop that evaluates all open positions for exit/hedge opportunities."""
        logger.info("[HedgeEngine] Starting scan for early exit and hedge opportunities...")
        
        while self._running:
            try:
                open_positions = db.get_open_positions()
                
                for pos in open_positions:
                    market_id = pos['market_id']
                    market_question = pos['market_question']
                    token_id = pos['token_id']
                    entry_price = pos['entry_price']
                    side = pos['side'] # usually BUY
                    size_usd = pos['size_usd']
                    
                    # 1. Get live price (Simulated here)
                    current_price = self._simulate_current_price(entry_price)
                    
                    # 2. Evaluate Take Profit (Sell Early)
                    if current_price - entry_price >= self.take_profit_threshold:
                        logger.info(f"[HedgeEngine] 💰 TAKE PROFIT TRIGGERED on '{market_question}'")
                        logger.info(f"[HedgeEngine] Entry: ${entry_price:.3f} | Current: ${current_price:.3f} | Target Reached!")
                        
                        # Execute limit SELL order
                        orders.place_strategic_limit_order(
                            market_id=market_id,
                            market_question=market_question,
                            token_id=token_id,
                            side="SELL",
                            price=current_price, # Set sell limit at the new high price
                            size_usd=size_usd,
                            strategy="take_profit"
                        )
                        
                        # Mark position as closed in DB
                        db.close_position(market_id, exit_price=current_price)
                        continue
                        
                    # 3. Evaluate Hedge (Stop Loss)
                    if entry_price - current_price >= self.stop_loss_threshold:
                        logger.warning(f"[HedgeEngine] 🛡️ HEDGE TRIGGERED on '{market_question}'")
                        logger.warning(f"[HedgeEngine] Entry: ${entry_price:.3f} | Dropped to: ${current_price:.3f}. Seeking correlated hedge.")
                        
                        # In production, we'd find the correlated spread/moneyline market and buy it.
                        # For now, we mock the hedge order execution.
                        hedge_market_question = f"HEDGE: Inverse of {market_question}"
                        orders.place_strategic_limit_order(
                            market_id=f"hedge_{market_id}",
                            market_question=hedge_market_question,
                            token_id=f"hedge_{token_id}",
                            side="BUY",
                            price=0.50, # mock price
                            size_usd=size_usd * 0.5, # Hedge with half size
                            strategy="defensive_hedge"
                        )
                        
                        # Update DB to reflect we took action (mock close or update)
                        db.close_position(market_id, exit_price=current_price)

            except Exception as e:
                logger.error(f"[HedgeEngine] Error in scan loop: {e}")
            
            # Poll every 10 seconds
            time.sleep(10)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self.scan_open_positions, daemon=True)
        self._thread.start()
        logger.info("[HedgeEngine] Engine started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("[HedgeEngine] Engine stopped")

hedge_engine = HedgeEngine()
