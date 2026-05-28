import time
import threading
from typing import List, Dict
from loguru import logger

from bot import config
from bot.order_manager import orders

class GridEngine:
    """
    Phase 5: Grid & Portfolio Construction Engine
    Instead of placing a single order at one price, this engine deploys capital
    across a "ladder" or "grid" of limit orders at varying price points.
    This captures volatility and averages down entry costs.
    """
    def __init__(self):
        self._running = False
        self._thread = None
        # How many levels to split the order into
        self.grid_levels = 3 
        # Price drop between each level
        self.step_size = 0.05 

    def place_grid_orders(self, market_id: str, market_question: str, token_id: str, side: str, base_price: float, total_size_usd: float):
        """
        Splits a single position into a grid of smaller limit orders.
        E.g., $30 total becomes $10 @ 40c, $10 @ 35c, $10 @ 30c
        """
        size_per_level = total_size_usd / self.grid_levels
        
        logger.info(f"[GridEngine] 🕸️ Deploying {self.grid_levels}-level Grid on '{market_question}'")
        
        for i in range(self.grid_levels):
            # For BUY, we ladder down (cheaper). For SELL, we ladder up (more expensive).
            price_adjustment = (i * self.step_size)
            grid_price = base_price - price_adjustment if side == "BUY" else base_price + price_adjustment
            
            # Ensure price stays within logical bounds (0.01 to 0.99)
            grid_price = max(0.01, min(0.99, grid_price))
            
            logger.info(f"[GridEngine] Level {i+1}: {side} ${size_per_level:.2f} @ {grid_price:.3f}")
            
            orders.place_strategic_limit_order(
                market_id=f"{market_id}_lvl_{i}", # Unique ID per grid level
                market_question=f"{market_question} (Grid L{i+1})",
                token_id=token_id,
                side=side,
                price=grid_price,
                size_usd=size_per_level,
                strategy="grid_trading"
            )

    def scan_for_volatility(self):
        """
        Background scanner that finds highly volatile markets
        and automatically deploys a grid to capture the swings.
        """
        logger.info("[GridEngine] Scanning for high-volatility grid opportunities...")
        
        while self._running:
            try:
                # Bypass simulated mock targets when live trading is active
                if not config.DRY_RUN:
                    time.sleep(15)
                    continue
                # In production, scan for markets with high volume and large spreads
                # For this implementation, we simulate finding a volatile market
                
                # Mock volatile market
                target_market = "Will the US enter a recession in 2026?"
                base_prob = 0.50
                
                # We deploy a wide grid around 50 cents to capture the chop
                self.place_grid_orders(
                    market_id="mock_recession_market",
                    market_question=target_market,
                    token_id="0xmock_token",
                    side="BUY",
                    base_price=base_prob,
                    total_size_usd=config.POSITION_SIZE_USD
                )
                
                # Sleep heavily so it doesn't spam grids
                time.sleep(120)

            except Exception as e:
                logger.error(f"[GridEngine] Error in scan loop: {e}")
            
            time.sleep(10)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self.scan_for_volatility, daemon=True)
        self._thread.start()
        logger.info("[GridEngine] Engine started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("[GridEngine] Engine stopped")

grid_engine = GridEngine()
