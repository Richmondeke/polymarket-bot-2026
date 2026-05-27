"""
bot/strategy_engine.py — Signal combiner and core logic loop.
Connects the Whale Tracker events to the Order Manager.
"""
from loguru import logger

from bot import config
from bot.whale_tracker import whale_tracker, WhaleTrade
from bot.order_manager import orders
from bot.stink_bid import stink_bid_engine
from bot.news_sentiment import news_engine
from bot.arbitrage_engine import arbitrage_engine
from bot.cross_line_arb import cross_line_engine
from bot.repricing_engine import repricing_engine
from bot.hedge_engine import hedge_engine
from bot.grid_engine import grid_engine
from bot.risk_manager import risk


class StrategyEngine:
    """Coordinates trading signals and execution."""

    def __init__(self):
        self._running = False

    def _on_whale_trade(self, trade: WhaleTrade):
        """Handler for new whale trades."""
        logger.info(f"[Strategy] Evaluating whale trade signal: {trade}")

        if risk.kill_switch_active:
            return

        # Simple mirror strategy: copy the exact same side and token
        # You could add AI sentiment analysis here before proceeding

        # Calculate position size
        # Assuming implied prob is close to the price the whale got
        prob = trade.price if trade.side == "BUY" else (1 - trade.price)
        size_usd = risk.calculate_position_size(
            win_probability=prob,
            current_balance=config.POSITION_SIZE_USD * 10, # Mock balance for size calc if needed, risk manager will cap it
        )
        
        # In this basic V1, we just use the fixed config size, Risk Manager applies Kelly limits
        size_usd = config.POSITION_SIZE_USD

        # Execute
        orders.place_copy_order(
            market_id=trade.market_id,
            market_question=trade.market_question,
            token_id=trade.token_id,
            side=trade.side,
            current_price=trade.price,
            size_usd=size_usd,
            whale_address=trade.whale_address,
        )

    def start(self):
        if self._running:
            return
        logger.info("[Strategy] Starting core engine…")
        
        # Register event listeners
        whale_tracker.on_whale_trade(self._on_whale_trade)
        
        # Start subsystems
        whale_tracker.start()
        stink_bid_engine.start()
        news_engine.start()
        arbitrage_engine.start()
        cross_line_engine.start()
        repricing_engine.start()
        hedge_engine.start()
        grid_engine.start()
        
        self._running = True
        logger.info("[Strategy] Engine started")

    def stop(self):
        self._running = False
        grid_engine.stop()
        hedge_engine.stop()
        repricing_engine.stop()
        cross_line_engine.stop()
        arbitrage_engine.stop()
        news_engine.stop()
        stink_bid_engine.stop()
        whale_tracker.stop()
        logger.info("[Strategy] Engine stopped")


# Singleton
engine = StrategyEngine()
