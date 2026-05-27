"""
bot/config.py — Configuration loader and validator.
Loads all settings from environment / .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

# Resolve project root and load .env
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def _get(key: str, default=None, required: bool = False):
    val = os.getenv(key, default)
    if required and not val:
        raise EnvironmentError(
            f"[Config] Missing required environment variable: {key}\n"
            f"  → Copy .env.example to .env and fill in your values."
        )
    return val


def _get_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _get_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, str(default)).strip().lower()
    return val in ("true", "1", "yes")


# ── Wallet / Blockchain ─────────────────────────────────────────────
POLYGON_PRIVATE_KEY: str = _get("POLYGON_PRIVATE_KEY", required=False) or ""
POLYGON_WALLET_ADDRESS: str = _get("POLYGON_WALLET_ADDRESS", required=False) or ""
POLYGON_RPC_URL: str = _get(
    "POLYGON_RPC_URL",
    "https://polygon-rpc.com",
)
CHAIN_ID: int = 137  # Polygon Mainnet

# ── Polymarket API Credentials ───────────────────────────────────────
POLY_API_KEY: str = _get("POLY_API_KEY") or ""
POLY_API_SECRET: str = _get("POLY_API_SECRET") or ""
POLY_API_PASSPHRASE: str = _get("POLY_API_PASSPHRASE") or ""

CLOB_HOST: str = "https://clob.polymarket.com"
GAMMA_HOST: str = "https://gamma-api.polymarket.com"
DATA_HOST: str = "https://data-api.polymarket.com"

# ── Trading Mode ────────────────────────────────────────────────────
DRY_RUN: bool = _get_bool("DRY_RUN", True)
LIVE_TRADING: bool = _get_bool("LIVE_TRADING", False)

if LIVE_TRADING and DRY_RUN:
    logger.warning("[Config] LIVE_TRADING=true overrides DRY_RUN. Bot will execute REAL orders.")
    DRY_RUN = False

if not LIVE_TRADING:
    DRY_RUN = True

# ── Position Sizing ─────────────────────────────────────────────────
POSITION_SIZE_USD: float = _get_float("POSITION_SIZE_USD", 2.0)
MAX_POSITION_SIZE_USD: float = _get_float("MAX_POSITION_SIZE_USD", 5.0)
KELLY_FRACTION: float = _get_float("KELLY_FRACTION", 0.25)

# ── Risk Controls ───────────────────────────────────────────────────
DAILY_STOP_LOSS_PCT: float = _get_float("DAILY_STOP_LOSS_PCT", 5.0)
MAX_DRAWDOWN_PCT: float = _get_float("MAX_DRAWDOWN_PCT", 15.0)
MAX_OPEN_POSITIONS: int = _get_int("MAX_OPEN_POSITIONS", 10)
MAX_RESOLUTION_DAYS: float = _get_float("MAX_RESOLUTION_DAYS", 0.0) # 0 means unlimited, >0 filters for short-term resolution


# ── Whale Tracker ───────────────────────────────────────────────────
TOP_N_WHALES: int = _get_int("TOP_N_WHALES", 5)
WHALE_MIN_WIN_RATE: float = _get_float("WHALE_MIN_WIN_RATE", 70.0)
WHALE_MIN_VOLUME: float = _get_float("WHALE_MIN_VOLUME", 10000.0)
WHALE_POLL_INTERVAL: int = _get_int("WHALE_POLL_INTERVAL", 60)
LEADERBOARD_REFRESH_HOURS: int = _get_int("LEADERBOARD_REFRESH_HOURS", 6)

# ── Stink Bid ───────────────────────────────────────────────────────
STINK_BID_ENABLED: bool = _get_bool("STINK_BID_ENABLED", True)
STINK_BID_DISCOUNT: float = _get_float("STINK_BID_DISCOUNT", 30.0)
STINK_BID_MIN_PROB: float = _get_float("STINK_BID_MIN_PROB", 0.65)
STINK_BID_MAX_OPEN: int = _get_int("STINK_BID_MAX_OPEN", 3)

# ── Dashboard ───────────────────────────────────────────────────────
DASHBOARD_PORT: int = _get_int("DASHBOARD_PORT", 5000)
DASHBOARD_HOST: str = _get("DASHBOARD_HOST", "0.0.0.0")

# ── AI Scoring ──────────────────────────────────────────────────────
GEMINI_API_KEY: str = _get("GEMINI_API_KEY") or ""
AI_SCORING_ENABLED: bool = _get_bool("AI_SCORING_ENABLED", False)

# ── Email Notifications ──────────────────────────────────────────────
SMTP_SERVER: str = _get("SMTP_SERVER") or ""
SMTP_PORT: int = _get_int("SMTP_PORT", 587)
SMTP_USERNAME: str = _get("SMTP_USERNAME") or ""
SMTP_PASSWORD: str = _get("SMTP_PASSWORD") or ""
NOTIFICATION_EMAIL: str = _get("NOTIFICATION_EMAIL") or ""

# ── Logging ─────────────────────────────────────────────────────────
LOG_LEVEL: str = _get("LOG_LEVEL", "INFO").upper()
LOG_FILE: str = str(_ROOT / _get("LOG_FILE", "data/bot.log"))

# ── Paths ────────────────────────────────────────────────────────────
DATA_DIR: Path = _ROOT / "data"
DB_PATH: str = str(DATA_DIR / "trades.db")

DATA_DIR.mkdir(parents=True, exist_ok=True)


def validate():
    """Call at startup to surface any missing critical config."""
    issues = []

    if LIVE_TRADING:
        if not POLYGON_PRIVATE_KEY:
            issues.append("POLYGON_PRIVATE_KEY required for live trading")
        if not POLY_API_KEY:
            issues.append("POLY_API_KEY required for live trading")
        if not POLY_API_SECRET:
            issues.append("POLY_API_SECRET required for live trading")
        if not POLY_API_PASSPHRASE:
            issues.append("POLY_API_PASSPHRASE required for live trading")

    if issues:
        for issue in issues:
            logger.error(f"[Config] ❌ {issue}")
        raise EnvironmentError("Fix config issues above before starting live trading.")

    mode = "🔴 LIVE TRADING" if LIVE_TRADING else "🟡 DRY RUN"
    logger.info(f"[Config] Mode: {mode}")
    logger.info(f"[Config] Position size: ${POSITION_SIZE_USD} | Stop-loss: {DAILY_STOP_LOSS_PCT}%")
    logger.info(f"[Config] Whales: top-{TOP_N_WHALES} (min {WHALE_MIN_WIN_RATE}% win rate)")
    logger.info(f"[Config] Stink bid: {'enabled' if STINK_BID_ENABLED else 'disabled'} @ -{STINK_BID_DISCOUNT}%")


def is_market_fast_resolving(market: dict) -> bool:
    """Return True if market resolves within MAX_RESOLUTION_DAYS. Always True if MAX_RESOLUTION_DAYS is 0."""
    if not MAX_RESOLUTION_DAYS:
        return True
    
    end_date_str = market.get("endDate")
    if not end_date_str:
        return False
        
    from datetime import datetime, timezone, timedelta
    try:
        # Standard ISO format: '2026-05-25T00:00:00Z'
        end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        time_left = end_dt - datetime.now(timezone.utc)
        return time_left <= timedelta(days=MAX_RESOLUTION_DAYS)
    except Exception:
        return False

