#!/usr/bin/env python3
"""
scripts/test_email.py — Verify SMTP config and view email template layouts.
Fires a test trade execution alert, profit alert, and daily performance report.
"""
import sys
from pathlib import Path
from loguru import logger

# Add project root to path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(_ROOT))

from bot import config
from bot.notifier import notifier


def main():
    logger.info("Starting SMTP Email Verification Tool...")
    
    # 1. Print configuration summary (hiding password)
    print("="*50)
    print("SMTP CONFIGURATION CHECK")
    print("="*50)
    print(f"SMTP Server:      {config.SMTP_SERVER}")
    print(f"SMTP Port:        {config.SMTP_PORT}")
    print(f"SMTP Username:    {config.SMTP_USERNAME}")
    print(f"SMTP Password:    {'*' * len(config.SMTP_PASSWORD) if config.SMTP_PASSWORD else 'None'}")
    print(f"Recipient Email:  {config.NOTIFICATION_EMAIL}")
    print("="*50)

    # 2. Check if SMTP is configured
    if not all([config.SMTP_SERVER, config.SMTP_PORT, config.SMTP_USERNAME, config.SMTP_PASSWORD, config.NOTIFICATION_EMAIL]):
        logger.error("❌ Configuration is incomplete! Please populate SMTP credentials in your .env file.")
        print("\nRequired fields in .env:")
        print("SMTP_SERVER=smtp.gmail.com")
        print("SMTP_PORT=587")
        print("SMTP_USERNAME=your-gmail@gmail.com")
        print("SMTP_PASSWORD=your-app-password")
        print("NOTIFICATION_EMAIL=your-recipient-email@gmail.com")
        sys.exit(1)

    logger.info("SMTP configuration looks complete. Proceeding to send test emails...")

    # 3. Test Trade Execution Alert
    logger.info("Sending simulated Trade Execution Alert...")
    test_trade = {
        "side": "BUY",
        "size_shares": 50.0,
        "price": 0.650,
        "strategy": "news_sentiment",
        "market_question": "Will AI-created music win a Grammy Award in 2026?",
        "dry_run": 1
    }
    try:
        notifier.send_trade_alert(test_trade)
        logger.info("✓ Trade Alert email task dispatched to background thread.")
    except Exception as e:
        logger.error(f"❌ Failed to dispatch Trade Alert: {e}")

    # 4. Test Profit Realized Alert
    logger.info("Sending simulated Profit Realized Card...")
    try:
        notifier.send_profit_alert(
            market_question="Will SpaceX successfully land Starship on Mars by end of 2026?",
            realized_pnl=42.50,
            size_usd=50.0,
            entry_price=0.450,
            exit_price=0.875,
            strategy="whale_copy"
        )
        logger.info("✓ Profit Alert email task dispatched to background thread.")
    except Exception as e:
        logger.error(f"❌ Failed to dispatch Profit Alert: {e}")

    # 5. Test Daily Report
    logger.info("Sending simulated Daily Performance Report...")
    try:
        # We run this synchronously so we can confirm completion before script exits
        notifier.send_daily_report()
        logger.info("✓ Daily Report compiled and sent successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to compile or send Daily Report: {e}")

    print("\n" + "="*50)
    print("🎉 Verification Complete!")
    print("Please check your email inbox (and spam folder) for:")
    print("1. [DRY RUN] Trade Executed: BUY 50.00 Shares")
    print("2. [DRY RUN] Position Closed: +$42.50 USDC")
    print("3. [DRY RUN] Polymarket Bot Daily Report")
    print("="*50)


if __name__ == "__main__":
    main()
