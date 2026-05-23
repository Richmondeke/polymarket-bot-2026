"""
main.py — Entry point for Polymarket Bot.
Starts the background strategy engine and runs the Flask dashboard.
"""
import sys
import threading
import signal
import time
from loguru import logger

from bot import config
from bot.database import init_db
from bot.client import clob
from bot.risk_manager import risk
from bot.strategy_engine import engine
from dashboard.app import start_dashboard


def setup_logging():
    logger.remove()
    logger.add(sys.stdout, level=config.LOG_LEVEL, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")
    logger.add(config.LOG_FILE, level=config.LOG_LEVEL, rotation="10 MB", retention="7 days")


def shutdown_handler(sig, frame):
    logger.critical("\n[Main] 🛑 Shutdown signal received.")
    logger.info("[Main] Cancelling open orders and stopping engine...")
    from bot.order_manager import orders
    orders.emergency_cancel_all()
    engine.stop()
    
    # Record final balance for today's PnL
    final_balance = clob.get_usdc_balance()
    risk.record_daily_close(final_balance)
    
    logger.info("[Main] Shutdown complete. Exiting.")
    sys.exit(0)


def main():
    setup_logging()
    logger.info("="*50)
    logger.info("🚀 Starting Polymarket Autonomous Bot")
    logger.info("="*50)

    # 1. Validate Config & Init DB
    config.validate()
    init_db()

    # 2. Check Balances & Set Daily Risk Baseline
    balance = clob.get_usdc_balance()
    logger.info(f"[Main] Current Polygon USDC Balance: ${balance:.2f}")
    risk.set_daily_start_balance(balance)

    # 3. Register graceful shutdown
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # 4. Start Strategy Engine in background
    engine_thread = threading.Thread(target=engine.start, name="StrategyEngine", daemon=True)
    engine_thread.start()

    # 5. Start Flask Dashboard (Blocks main thread)
    start_dashboard()


if __name__ == "__main__":
    main()
