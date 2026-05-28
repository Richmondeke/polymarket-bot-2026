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

    def _simulate_current_price(self, entry_price: float, current_db_price: float = None) -> float:
        """
        Get current price. Uses actual database/live price in live mode,
        simulates movement in dry-run/mock mode.
        """
        if not config.DRY_RUN:
            return current_db_price if current_db_price is not None else entry_price

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
                    
                    # 1. Get live price (Simulated in dry run, actual in live)
                    current_price = self._simulate_current_price(entry_price, pos.get('current_price'))
                    
                    # 2. Evaluate Take Profit (Sell Early)
                    is_take_profit = False
                    profit_reason = ""
                    
                    if entry_price <= 0.20:
                        price_increase_pct = (current_price - entry_price) / max(entry_price, 0.001)
                        if price_increase_pct >= 0.50:
                            is_take_profit = True
                            profit_reason = f"Percentage Target Reached (+{price_increase_pct:.1%})"
                    else:
                        if current_price - entry_price >= self.take_profit_threshold:
                            is_take_profit = True
                            profit_reason = f"Absolute Target Reached (+${current_price - entry_price:.3f})"
                            
                    if is_take_profit:
                        logger.info(f"[HedgeEngine] 💰 TAKE PROFIT TRIGGERED on '{market_question}'")
                        logger.info(f"[HedgeEngine] Entry: ${entry_price:.3f} | Current: ${current_price:.3f} | {profit_reason}")
                        
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
                        
                        # Mark position as closed in DB only in Dry Run (simulation)
                        if config.DRY_RUN:
                            db.close_position(market_id, exit_price=current_price)
                        continue
                        
                    # 3. Evaluate Hedge (Stop Loss)
                    if entry_price - current_price >= self.stop_loss_threshold:
                        logger.warning(f"[HedgeEngine] 🛡️ STOP LOSS / HEDGE TRIGGERED on '{market_question}'")
                        logger.warning(f"[HedgeEngine] Entry: ${entry_price:.3f} | Dropped to: ${current_price:.3f}. Taking defensive action.")
                        
                        if config.DRY_RUN:
                            # In Dry Run, we mock the hedge order execution.
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
                            db.close_position(market_id, exit_price=current_price)
                        else:
                            # In Live mode, execute a stop-loss sell order to exit the position and cut losses.
                            logger.info(f"[HedgeEngine] Executing live stop-loss SELL order for '{market_question}' @ ${current_price:.3f}")
                            orders.place_strategic_limit_order(
                                market_id=market_id,
                                market_question=market_question,
                                token_id=token_id,
                                side="SELL",
                                price=current_price,
                                size_usd=size_usd,
                                strategy="stop_loss"
                            )

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
