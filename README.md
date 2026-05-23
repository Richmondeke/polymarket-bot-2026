# Polymarket Autonomous Bot

A fully automated Polymarket trading bot with a whale copy-trading strategy, stink-bid failsafe, risk controls, and a Bloomberg-style real-time dashboard.

## Features
- **Whale Copy-Trading**: Automatically discovers top whales from the leaderboard and mirrors their trades.
- **Stink Bids**: Automatically places deep discount limit BUY orders (-30%) on high liquidity markets to catch flash crashes.
- **Risk Management**: Enforces daily stop-loss (e.g. 5%), max portfolio drawdown (e.g. 15%), and prevents duplicate positions. 
- **Real-time Dashboard**: Local web app providing live P&L charting, active positions, recent fills, and a manual Kill Switch.
- **Dry-Run Mode**: Safely simulate trades without risking funds.

## Setup

1. **Install dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   Copy the `.env.example` file to `.env` and fill in your details:
   ```bash
   cp .env.example .env
   ```
   You will need:
   - Your Polygon Wallet Private Key
   - A Polygon RPC URL (e.g., from Alchemy or Infura)
   - Your Polymarket API Credentials (from Profile -> Builders)

3. **Initialize Database**
   ```bash
   python scripts/setup_db.py
   ```

4. **Run Pre-flight Checks**
   ```bash
   python scripts/dry_run_test.py
   ```

## Running the Bot

By default, `.env` configures the bot in `DRY_RUN=true`. Start the bot:

```bash
python main.py
```

Open your browser to `http://localhost:5000` to view the dashboard.

When you are ready to trade with real funds, update `.env`:
```
DRY_RUN=false
LIVE_TRADING=true
```

## Docker Deployment (Optional)

You can run the bot in a Docker container for 24/7 execution:

```bash
# Create Dockerfile
echo -e "FROM python:3.11-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install -r requirements.txt\nCOPY . .\nCMD [\"python\", \"main.py\"]" > Dockerfile

docker-compose up -d
```
