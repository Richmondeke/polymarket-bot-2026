"""
main.py — Entry point for Polymarket Bot.
Starts the background strategy engine and runs the Flask dashboard.
"""
import sys
import threading
import signal
import time
import schedule
from loguru import logger

from bot import config
from bot.database import init_db
from bot.client import clob
from bot.risk_manager import risk
from bot.strategy_engine import engine
from bot.notifier import notifier
from dashboard.app import start_dashboard

scheduler_running = True


def setup_logging():
    logger.remove()
    logger.add(sys.stdout, level=config.LOG_LEVEL, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")
    logger.add(config.LOG_FILE, level=config.LOG_LEVEL, rotation="10 MB", retention="7 days")


def run_scheduler_loop():
    global scheduler_running
    logger.info("[Scheduler] Background scheduler loop started.")
    while scheduler_running:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"[Scheduler] Error running pending jobs: {e}")
        time.sleep(10)
    logger.info("[Scheduler] Background scheduler loop stopped.")


def shutdown_handler(sig, frame):
    global scheduler_running
    logger.critical("\n[Main] 🛑 Shutdown signal received.")
    logger.info("[Main] Cancelling open orders and stopping engine...")
    
    scheduler_running = False
    from bot.order_manager import orders
    orders.emergency_cancel_all()
    engine.stop()
    
    # Record final balance for today's PnL
    final_balance = clob.get_usdc_balance()
    risk.record_daily_close(final_balance)
    
    logger.info("[Main] Shutdown complete. Exiting.")
    sys.exit(0)


def _backfill_end_dates():
    """Fetch and store endDate for any open positions that are missing it."""
    import requests as _req
    import sqlite3 as _sqlite3
    from bot import database as db
    positions = [p for p in db.get_open_positions() if not p.get("end_date")]
    if not positions:
        return
    logger.info(f"[Main] Backfilling end_date for {len(positions)} open position(s)...")
    con = _sqlite3.connect(config.DB_PATH)
    for p in positions:
        mid = p["market_id"]
        try:
            # Gamma API requires conditionId as a query param, not path segment
            r = _req.get(
                "https://gamma-api.polymarket.com/markets",
                params={"conditionId": mid},
                timeout=8
            )
            if r.ok:
                data = r.json()
                items = data if isinstance(data, list) else data.get("results", [])
                if items:
                    end_date = items[0].get("endDate") or items[0].get("endDateIso")
                    if end_date:
                        con.execute("UPDATE positions SET end_date=? WHERE market_id=?", (end_date, mid))
                        con.commit()
                        logger.info(f"[Main] ✅ end_date set → {end_date} ({mid[:20]}...)")
        except Exception as e:
            logger.warning(f"[Main] Could not backfill end_date for {mid}: {e}")
        time.sleep(0.3)
    con.close()
    logger.info("[Main] End date backfill complete.")


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
    
    # Initialize milestone alerts based on current starting equity
    status = risk.get_status(balance)
    notifier.init_milestones(status.get("total_equity", balance))

    # Backfill any missing end_dates for open positions (runs in background)
    threading.Thread(target=_backfill_end_dates, name="EndDateBackfill", daemon=True).start()


    # 3. Register graceful shutdown
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # 4. Start Strategy Engine in background
    engine_thread = threading.Thread(target=engine.start, name="StrategyEngine", daemon=True)
    engine_thread.start()

    # 5. Start Daily Notification Scheduler
    # Register daily report at 23:50
    schedule.every().day.at("23:50").do(notifier.send_daily_report)
    logger.info("[Scheduler] Registered daily report at 23:50.")
    
    scheduler_thread = threading.Thread(target=run_scheduler_loop, name="Scheduler", daemon=True)
    scheduler_thread.start()

    # 6. Start Flask Dashboard (Blocks main thread)
    start_dashboard()


if __name__ == "__main__":
    main()
