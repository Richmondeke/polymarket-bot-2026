"""
run_bot.py — Headless one-shot runner for GitHub Actions.
Runs all strategies once then exits. No Flask server, no infinite loops.
Designed to be triggered every 10 minutes via GitHub Actions cron.
"""
import sys
import time
import signal
from loguru import logger

# ── Timeout safety: kill after 7 minutes ────────────────────────────
def _timeout_handler(sig, frame):
    logger.warning("[Runner] 7-minute timeout reached. Exiting gracefully.")
    sys.exit(0)

signal.signal(signal.SIGALRM, signal.SIGALRM)
try:
    signal.alarm(420)  # 7 minutes
except AttributeError:
    pass  # Windows doesn't support SIGALRM — that's fine, GH Actions is Linux


def setup_logging():
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <level>{message}</level>"
    )


def main():
    setup_logging()
    start = time.time()
    logger.info("=" * 55)
    logger.info("🤖 Polymarket Bot — GitHub Actions Run")
    logger.info("=" * 55)

    # ── 1. Init ──────────────────────────────────────────────────────
    from bot import config
    config.validate()

    from bot.database import init_db
    init_db()

    from bot.client import clob
    from bot.risk_manager import risk

    balance = clob.get_usdc_balance()
    logger.info(f"[Runner] Balance: ${balance:.2f} | Mode: {'LIVE' if config.LIVE_TRADING else 'DRY RUN'}")
    risk.set_daily_start_balance(balance)

    if risk.kill_switch_active:
        logger.warning("[Runner] Kill switch is active. Skipping all trades.")
        return

    # ── 2. Whale Tracker refresh ─────────────────────────────────────
    try:
        logger.info("[Runner] Refreshing whale watchlist...")
        from bot.whale_tracker import WhaleTrackerEngine
        wt = WhaleTrackerEngine()
        wt._refresh_watchlist()
        logger.info("[Runner] ✅ Whale list refreshed")
    except Exception as e:
        logger.error(f"[Runner] Whale refresh error: {e}")

    # ── 3. StinkBid scan ─────────────────────────────────────────────
    try:
        logger.info("[Runner] Running StinkBid scan...")
        from bot.stink_bid import StinkBidEngine
        sb = StinkBidEngine()
        sb._scan_and_place()
        logger.info("[Runner] ✅ StinkBid scan complete")
    except Exception as e:
        logger.error(f"[Runner] StinkBid error: {e}")

    # ── 4. News Sentiment scan ───────────────────────────────────────
    try:
        logger.info("[Runner] Running News Sentiment scan...")
        from bot.news_sentiment import NewsSentimentEngine
        ns = NewsSentimentEngine()
        ns._scan_and_trade()
        logger.info("[Runner] ✅ News Sentiment scan complete")
    except Exception as e:
        logger.error(f"[Runner] News Sentiment error: {e}")

    # ── 5. Arbitrage scan ────────────────────────────────────────────
    try:
        logger.info("[Runner] Running Arbitrage scan...")
        from bot.arbitrage_engine import ArbitrageEngine
        arb = ArbitrageEngine()
        arb._scan_and_trade()
        logger.info("[Runner] ✅ Arbitrage scan complete")
    except Exception as e:
        logger.error(f"[Runner] Arbitrage error: {e}")

    # ── 6. End-date backfill ─────────────────────────────────────────
    try:
        import requests as _req
        from bot.database import get_open_positions
        import psycopg2 if False else None  # noqa — handled in database.py
        from bot import database as db_module
        missing = [p for p in get_open_positions() if not p.get("end_date")]
        if missing:
            logger.info(f"[Runner] Backfilling end_date for {len(missing)} positions...")
            import sqlite3 as _sqlite, os as _os
            _db_url = _os.getenv("DATABASE_URL")
            for p in missing:
                mid = p["market_id"]
                try:
                    r = _req.get(
                        "https://gamma-api.polymarket.com/markets",
                        params={"conditionId": mid}, timeout=8
                    )
                    if r.ok:
                        items = r.json() if isinstance(r.json(), list) else r.json().get("results", [])
                        if items:
                            end_date = items[0].get("endDate")
                            if end_date and _db_url:
                                import psycopg2 as _pg
                                _c = _pg.connect(_db_url)
                                _c.cursor().execute("UPDATE positions SET end_date=%s WHERE market_id=%s", (end_date, mid))
                                _c.commit(); _c.close()
                            elif end_date:
                                _c = _sqlite.connect(config.DB_PATH)
                                _c.execute("UPDATE positions SET end_date=? WHERE market_id=?", (end_date, mid))
                                _c.commit(); _c.close()
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"[Runner] End-date backfill skipped: {e}")

    # ── 7. Summary ───────────────────────────────────────────────────
    elapsed = time.time() - start
    final_balance = clob.get_usdc_balance()
    logger.info("=" * 55)
    logger.info(f"[Runner] ✅ Run complete in {elapsed:.1f}s")
    logger.info(f"[Runner] Final balance: ${final_balance:.2f}")
    logger.info("=" * 55)


if __name__ == "__main__":
    main()
