"""
scripts/dry_run_test.py
Validates API connections and configuration without placing orders.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from loguru import logger
from bot import config
from bot.client import clob, gamma, data_api

def main():
    logger.info("--- Starting Pre-flight Checks ---")
    
    # 1. Config Check
    logger.info("1. Validating Config...")
    try:
        config.validate()
        logger.info("✅ Config OK")
    except Exception as e:
        logger.error(f"❌ Config Error: {e}")
        return

    # 2. Gamma API Check
    logger.info("2. Testing Gamma API (Markets)...")
    markets = gamma.get_active_markets(limit=5)
    if markets:
        logger.info(f"✅ Gamma API OK (found {len(markets)} markets)")
    else:
        logger.error("❌ Gamma API Failed")

    # 3. Data API Check
    logger.info("3. Testing Data API (Leaderboard)...")
    leaders = data_api.get_leaderboard(limit=3)
    if leaders:
        logger.info(f"✅ Data API OK (found {len(leaders)} leaders)")
    else:
        logger.error("❌ Data API Failed")

    # 4. CLOB Auth Check
    logger.info("4. Testing CLOB API (Auth & Balance)...")
    if not config.POLYGON_PRIVATE_KEY:
        logger.warning("⚠️ No private key provided. CLOB will be read-only.")
    else:
        balance = clob.get_usdc_balance()
        logger.info(f"✅ CLOB API OK. USDC Balance: ${balance:.2f}")

    logger.info("--- Pre-flight Complete ---")
    logger.info("You can now run: python main.py")


if __name__ == "__main__":
    main()
