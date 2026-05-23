"""
bot/database.py — SQLite persistence layer.
Handles all trade history, positions, P&L, whale watchlist, and system events.
"""
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from loguru import logger

from bot import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _conn():
    """Thread-safe SQLite connection context manager."""
    con = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Schema ──────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    market_id       TEXT    NOT NULL,
    market_question TEXT,
    side            TEXT    NOT NULL,   -- BUY or SELL
    price           REAL    NOT NULL,
    size_usd        REAL    NOT NULL,
    size_shares     REAL,
    order_id        TEXT,
    strategy        TEXT,               -- 'whale_copy' or 'stink_bid'
    whale_address   TEXT,
    status          TEXT    DEFAULT 'pending',  -- pending, filled, cancelled, failed
    fill_price      REAL,
    fill_time       TEXT,
    dry_run         INTEGER DEFAULT 1,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id       TEXT    NOT NULL UNIQUE,
    market_question TEXT,
    token_id        TEXT,
    side            TEXT    NOT NULL,
    entry_price     REAL    NOT NULL,
    current_price   REAL,
    size_shares     REAL    NOT NULL,
    size_usd        REAL    NOT NULL,
    unrealized_pnl  REAL    DEFAULT 0.0,
    strategy        TEXT,
    opened_at       TEXT    NOT NULL,
    updated_at      TEXT,
    is_open         INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT    NOT NULL UNIQUE,  -- YYYY-MM-DD
    starting_balance REAL,
    ending_balance  REAL,
    realized_pnl    REAL    DEFAULT 0.0,
    unrealized_pnl  REAL    DEFAULT 0.0,
    num_trades      INTEGER DEFAULT 0,
    num_wins        INTEGER DEFAULT 0,
    num_losses      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS whale_watchlist (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_address   TEXT    NOT NULL UNIQUE,
    display_name    TEXT,
    win_rate        REAL,
    total_volume    REAL,
    total_profit    REAL,
    last_trade_time TEXT,
    last_checked    TEXT,
    is_active       INTEGER DEFAULT 1,
    rank            INTEGER
);

CREATE TABLE IF NOT EXISTS system_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    event_type      TEXT    NOT NULL,  -- trade, risk, whale, error, info
    severity        TEXT    DEFAULT 'info',  -- info, warning, error, critical
    message         TEXT    NOT NULL,
    data            TEXT                -- JSON blob for extra context
);

CREATE INDEX IF NOT EXISTS idx_trades_market ON trades(market_id);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_time   ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_positions_open ON positions(is_open);
CREATE INDEX IF NOT EXISTS idx_events_time   ON system_events(timestamp);
"""


def init_db():
    """Initialize the database schema. Safe to call multiple times."""
    with _conn() as con:
        con.executescript(SCHEMA)
    logger.info(f"[DB] Initialized at {config.DB_PATH}")


# ── Trades ──────────────────────────────────────────────────────────

def log_trade(
    market_id: str,
    market_question: str,
    side: str,
    price: float,
    size_usd: float,
    size_shares: float = None,
    order_id: str = None,
    strategy: str = None,
    whale_address: str = None,
    status: str = "pending",
    dry_run: bool = True,
    notes: str = None,
) -> int:
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO trades
               (timestamp, market_id, market_question, side, price, size_usd,
                size_shares, order_id, strategy, whale_address, status, dry_run, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_now(), market_id, market_question, side.upper(), price, size_usd,
             size_shares, order_id, strategy, whale_address, status, int(dry_run), notes),
        )
        return cur.lastrowid


def update_trade_status(trade_id: int, status: str, fill_price: float = None):
    with _conn() as con:
        con.execute(
            "UPDATE trades SET status=?, fill_price=?, fill_time=? WHERE id=?",
            (status, fill_price, _now() if fill_price else None, trade_id),
        )


def update_trade_status_by_market(market_id: str, status: str):
    with _conn() as con:
        con.execute(
            "UPDATE trades SET status=? WHERE market_id=? AND status IN ('open', 'simulated')",
            (status, market_id)
        )


def get_escrowed_balance() -> float:
    """Return total USDC locked in active/pending orders (open/simulated)."""
    with _conn() as con:
        row = con.execute(
            "SELECT SUM(price * size_shares) FROM trades WHERE status IN ('open', 'simulated')"
        ).fetchone()
        return float(row[0] or 0.0)


def get_positions_market_value() -> float:
    """Return total market value of all open positions."""
    with _conn() as con:
        rows = con.execute(
            "SELECT current_price, entry_price, size_shares FROM positions WHERE is_open=1"
        ).fetchall()
        val = 0.0
        for r in rows:
            p = r["current_price"] if r["current_price"] is not None else r["entry_price"]
            val += p * r["size_shares"]
        return val


def get_recent_trades(limit: int = 50) -> List[Dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Positions ────────────────────────────────────────────────────────

def upsert_position(
    market_id: str,
    market_question: str,
    token_id: str,
    side: str,
    entry_price: float,
    size_shares: float,
    size_usd: float,
    strategy: str = None,
):
    with _conn() as con:
        existing = con.execute(
            "SELECT id FROM positions WHERE market_id=? AND is_open=1", (market_id,)
        ).fetchone()
        if existing:
            con.execute(
                """UPDATE positions SET current_price=?, updated_at=? WHERE market_id=? AND is_open=1""",
                (entry_price, _now(), market_id),
            )
        else:
            con.execute(
                """INSERT INTO positions
                   (market_id, market_question, token_id, side, entry_price, current_price,
                    size_shares, size_usd, strategy, opened_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (market_id, market_question, token_id, side.upper(), entry_price, entry_price,
                 size_shares, size_usd, strategy, _now(), _now()),
            )


def close_position(market_id: str, exit_price: float = None):
    with _conn() as con:
        con.execute(
            "UPDATE positions SET is_open=0, updated_at=?, current_price=? WHERE market_id=? AND is_open=1",
            (_now(), exit_price, market_id),
        )


def update_position_prices(prices: Dict[str, float]):
    """Bulk update current prices for open positions."""
    with _conn() as con:
        for market_id, price in prices.items():
            entry = con.execute(
                "SELECT entry_price, size_shares FROM positions WHERE market_id=? AND is_open=1",
                (market_id,),
            ).fetchone()
            if entry:
                upnl = (price - entry["entry_price"]) * entry["size_shares"]
                con.execute(
                    "UPDATE positions SET current_price=?, unrealized_pnl=?, updated_at=? WHERE market_id=? AND is_open=1",
                    (price, upnl, _now(), market_id),
                )


def get_open_positions() -> List[Dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM positions WHERE is_open=1 ORDER BY opened_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def position_exists(market_id: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT id FROM positions WHERE market_id=? AND is_open=1", (market_id,)
        ).fetchone()
    return row is not None


# ── Daily P&L ────────────────────────────────────────────────────────

def upsert_daily_pnl(
    date: str,
    starting_balance: float = None,
    ending_balance: float = None,
    realized_pnl: float = 0.0,
    unrealized_pnl: float = 0.0,
    num_trades: int = 0,
    num_wins: int = 0,
    num_losses: int = 0,
):
    with _conn() as con:
        existing = con.execute("SELECT id FROM daily_pnl WHERE date=?", (date,)).fetchone()
        if existing:
            con.execute(
                """UPDATE daily_pnl SET ending_balance=?, realized_pnl=?,
                   unrealized_pnl=?, num_trades=?, num_wins=?, num_losses=? WHERE date=?""",
                (ending_balance, realized_pnl, unrealized_pnl, num_trades, num_wins, num_losses, date),
            )
        else:
            con.execute(
                """INSERT INTO daily_pnl
                   (date, starting_balance, ending_balance, realized_pnl,
                    unrealized_pnl, num_trades, num_wins, num_losses)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (date, starting_balance, ending_balance, realized_pnl,
                 unrealized_pnl, num_trades, num_wins, num_losses),
            )


def get_pnl_history(days: int = 30) -> List[Dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM daily_pnl ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_today_pnl() -> Optional[Dict]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _conn() as con:
        row = con.execute("SELECT * FROM daily_pnl WHERE date=?", (today,)).fetchone()
    return dict(row) if row else None


# ── Whale Watchlist ──────────────────────────────────────────────────

def upsert_whale(
    proxy_address: str,
    display_name: str = None,
    win_rate: float = None,
    total_volume: float = None,
    total_profit: float = None,
    last_trade_time: str = None,
    rank: int = None,
):
    with _conn() as con:
        existing = con.execute(
            "SELECT id FROM whale_watchlist WHERE proxy_address=?", (proxy_address,)
        ).fetchone()
        if existing:
            con.execute(
                """UPDATE whale_watchlist SET display_name=?, win_rate=?, total_volume=?,
                   total_profit=?, last_trade_time=?, last_checked=?, rank=?, is_active=1
                   WHERE proxy_address=?""",
                (display_name, win_rate, total_volume, total_profit, last_trade_time,
                 _now(), rank, proxy_address),
            )
        else:
            con.execute(
                """INSERT INTO whale_watchlist
                   (proxy_address, display_name, win_rate, total_volume, total_profit,
                    last_trade_time, last_checked, rank)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (proxy_address, display_name, win_rate, total_volume, total_profit,
                 last_trade_time, _now(), rank),
            )


def get_active_whales() -> List[Dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM whale_watchlist WHERE is_active=1 ORDER BY rank ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def deactivate_all_whales():
    """Mark all whales as inactive (before refreshing list)."""
    with _conn() as con:
        con.execute("UPDATE whale_watchlist SET is_active=0")


# ── System Events ────────────────────────────────────────────────────

def log_event(
    event_type: str,
    message: str,
    severity: str = "info",
    data: Dict = None,
):
    with _conn() as con:
        con.execute(
            """INSERT INTO system_events (timestamp, event_type, severity, message, data)
               VALUES (?,?,?,?,?)""",
            (_now(), event_type, severity, message, json.dumps(data) if data else None),
        )


def get_recent_events(limit: int = 100) -> List[Dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM system_events ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
