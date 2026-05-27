"""
bot/database.py — Tri-mode persistence layer.
Firestore (Firebase) when FIREBASE_PROJECT_ID is set.
PostgreSQL (Supabase) when DATABASE_URL is set.
SQLite locally (default).
"""
import os
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from loguru import logger

from bot import config

# ── Mode detection ──────────────────────────────────────────────────
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
DATABASE_URL        = os.getenv("DATABASE_URL")
USE_FIREBASE        = bool(FIREBASE_PROJECT_ID)
USE_POSTGRES        = bool(DATABASE_URL) and not USE_FIREBASE

# ── Firebase routing (proxy all calls to firebase_db) ───────────────
if USE_FIREBASE:
    from bot.firebase_db import (  # noqa — re-export everything
        init_db, log_trade, update_trade_status, update_trade_status_by_market,
        get_escrowed_balance, get_positions_market_value, get_recent_trades,
        upsert_position, close_position, update_position_prices,
        get_open_positions, position_exists, get_total_realized_pnl,
        upsert_daily_pnl, get_pnl_history, get_today_pnl, get_initial_balance,
        upsert_whale, get_active_whales, deactivate_all_whales,
        log_event, get_recent_events,
    )
    logger.info("[DB] Mode: Firebase Firestore")
else:
    pass  # continue below with SQLite / PostgreSQL

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
    logger.info("[DB] Mode: PostgreSQL (Supabase cloud)")
else:
    import sqlite3
    logger.info(f"[DB] Mode: SQLite → {config.DB_PATH}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _q(sql: str) -> str:
    """Translate SQLite ? placeholders to PostgreSQL %s when needed."""
    return sql.replace("?", "%s") if USE_POSTGRES else sql


@contextmanager
def _conn():
    """Unified connection context manager for SQLite and PostgreSQL."""
    if USE_POSTGRES:
        con = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
    else:
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


def _fetchall(con, sql: str, params: tuple = ()) -> List[Dict]:
    """Execute a SELECT and return list of dicts regardless of DB mode."""
    cur = con.cursor()
    cur.execute(_q(sql), params)
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def _fetchone(con, sql: str, params: tuple = ()) -> Optional[Dict]:
    """Execute a SELECT and return one dict or None."""
    cur = con.cursor()
    cur.execute(_q(sql), params)
    row = cur.fetchone()
    return dict(row) if row else None


def _execute(con, sql: str, params: tuple = ()):
    """Execute a write statement."""
    cur = con.cursor()
    cur.execute(_q(sql), params)
    return cur


# ── Schema ──────────────────────────────────────────────────────────

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    market_id       TEXT    NOT NULL,
    market_question TEXT,
    side            TEXT    NOT NULL,
    price           REAL    NOT NULL,
    size_usd        REAL    NOT NULL,
    size_shares     REAL,
    order_id        TEXT,
    strategy        TEXT,
    whale_address   TEXT,
    status          TEXT    DEFAULT 'pending',
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
    end_date        TEXT,
    opened_at       TEXT    NOT NULL,
    updated_at      TEXT,
    is_open         INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT    NOT NULL UNIQUE,
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
    event_type      TEXT    NOT NULL,
    severity        TEXT    DEFAULT 'info',
    message         TEXT    NOT NULL,
    data            TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_market ON trades(market_id);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_time   ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_positions_open ON positions(is_open);
CREATE INDEX IF NOT EXISTS idx_events_time   ON system_events(timestamp);
"""

# PostgreSQL schema — separate statements, SERIAL instead of AUTOINCREMENT
SCHEMA_POSTGRES = [
    """CREATE TABLE IF NOT EXISTS trades (
        id              SERIAL PRIMARY KEY,
        timestamp       TEXT    NOT NULL,
        market_id       TEXT    NOT NULL,
        market_question TEXT,
        side            TEXT    NOT NULL,
        price           REAL    NOT NULL,
        size_usd        REAL    NOT NULL,
        size_shares     REAL,
        order_id        TEXT,
        strategy        TEXT,
        whale_address   TEXT,
        status          TEXT    DEFAULT 'pending',
        fill_price      REAL,
        fill_time       TEXT,
        dry_run         INTEGER DEFAULT 1,
        notes           TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS positions (
        id              SERIAL PRIMARY KEY,
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
        end_date        TEXT,
        opened_at       TEXT    NOT NULL,
        updated_at      TEXT,
        is_open         INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS daily_pnl (
        id              SERIAL PRIMARY KEY,
        date            TEXT    NOT NULL UNIQUE,
        starting_balance REAL,
        ending_balance  REAL,
        realized_pnl    REAL    DEFAULT 0.0,
        unrealized_pnl  REAL    DEFAULT 0.0,
        num_trades      INTEGER DEFAULT 0,
        num_wins        INTEGER DEFAULT 0,
        num_losses      INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS whale_watchlist (
        id              SERIAL PRIMARY KEY,
        proxy_address   TEXT    NOT NULL UNIQUE,
        display_name    TEXT,
        win_rate        REAL,
        total_volume    REAL,
        total_profit    REAL,
        last_trade_time TEXT,
        last_checked    TEXT,
        is_active       INTEGER DEFAULT 1,
        rank            INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS system_events (
        id              SERIAL PRIMARY KEY,
        timestamp       TEXT    NOT NULL,
        event_type      TEXT    NOT NULL,
        severity        TEXT    DEFAULT 'info',
        message         TEXT    NOT NULL,
        data            TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_trades_market ON trades(market_id)",
    "CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)",
    "CREATE INDEX IF NOT EXISTS idx_trades_time   ON trades(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_positions_open ON positions(is_open)",
    "CREATE INDEX IF NOT EXISTS idx_events_time   ON system_events(timestamp)",
]


def init_db():
    """Initialize the database schema. Safe to call multiple times."""
    with _conn() as con:
        if USE_POSTGRES:
            cur = con.cursor()
            for stmt in SCHEMA_POSTGRES:
                cur.execute(stmt)
        else:
            con.executescript(SCHEMA_SQLITE)
    logger.info(f"[DB] Schema initialized ({'PostgreSQL' if USE_POSTGRES else 'SQLite'})")


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
        if USE_POSTGRES:
            cur = con.cursor()
            cur.execute(
                """INSERT INTO trades
                   (timestamp, market_id, market_question, side, price, size_usd,
                    size_shares, order_id, strategy, whale_address, status, dry_run, notes)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (_now(), market_id, market_question, side.upper(), price, size_usd,
                 size_shares, order_id, strategy, whale_address, status, int(dry_run), notes),
            )
            return cur.fetchone()["id"]
        else:
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
        _execute(con,
            "UPDATE trades SET status=?, fill_price=?, fill_time=? WHERE id=?",
            (status, fill_price, _now() if fill_price else None, trade_id),
        )


def update_trade_status_by_market(market_id: str, status: str):
    with _conn() as con:
        _execute(con,
            "UPDATE trades SET status=? WHERE market_id=? AND status IN ('open', 'simulated')",
            (status, market_id)
        )


def get_escrowed_balance() -> float:
    with _conn() as con:
        row = _fetchone(con,
            "SELECT SUM(price * size_shares) as total FROM trades WHERE status IN ('open', 'simulated')"
        )
        return float((row or {}).get("total") or 0.0)


def get_positions_market_value() -> float:
    with _conn() as con:
        rows = _fetchall(con,
            "SELECT current_price, entry_price, size_shares FROM positions WHERE is_open=1"
        )
    val = 0.0
    for r in rows:
        p = r["current_price"] if r["current_price"] is not None else r["entry_price"]
        val += p * r["size_shares"]
    return val


def get_recent_trades(limit: int = 50) -> List[Dict]:
    with _conn() as con:
        return _fetchall(con,
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        )


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
    end_date: str = None,
):
    with _conn() as con:
        existing = _fetchone(con,
            "SELECT id, is_open FROM positions WHERE market_id=?", (market_id,)
        )
        if existing:
            if existing.get("is_open", 1) == 1:
                _execute(con,
                    "UPDATE positions SET current_price=?, updated_at=? WHERE market_id=?",
                    (entry_price, _now(), market_id),
                )
            else:
                _execute(con,
                    "UPDATE positions SET is_open=1, side=?, entry_price=?, current_price=?, size_shares=?, size_usd=?, strategy=?, opened_at=?, updated_at=? WHERE market_id=?",
                    (side.upper(), entry_price, entry_price, size_shares, size_usd, strategy, _now(), _now(), market_id),
                )
        else:
            _execute(con,
                """INSERT INTO positions
                   (market_id, market_question, token_id, side, entry_price, current_price,
                    size_shares, size_usd, strategy, end_date, opened_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (market_id, market_question, token_id, side.upper(), entry_price, entry_price,
                 size_shares, size_usd, strategy, end_date, _now(), _now()),
            )


def close_position(market_id: str, exit_price: float = None):
    with _conn() as con:
        _execute(con,
            "UPDATE positions SET is_open=0, updated_at=?, current_price=? WHERE market_id=? AND is_open=1",
            (_now(), exit_price, market_id),
        )


def update_position_prices(prices: Dict[str, float]):
    with _conn() as con:
        for market_id, price in prices.items():
            entry = _fetchone(con,
                "SELECT entry_price, size_shares FROM positions WHERE market_id=? AND is_open=1",
                (market_id,),
            )
            if entry:
                upnl = (price - entry["entry_price"]) * entry["size_shares"]
                _execute(con,
                    "UPDATE positions SET current_price=?, unrealized_pnl=?, updated_at=? WHERE market_id=? AND is_open=1",
                    (price, upnl, _now(), market_id),
                )


def get_open_positions() -> List[Dict]:
    with _conn() as con:
        return _fetchall(con,
            "SELECT * FROM positions WHERE is_open=1 ORDER BY opened_at DESC"
        )


def position_exists(market_id: str) -> bool:
    with _conn() as con:
        row = _fetchone(con,
            "SELECT id FROM positions WHERE market_id=? AND is_open=1", (market_id,)
        )
    return row is not None


def get_total_realized_pnl() -> float:
    with _conn() as con:
        row = _fetchone(con,
            "SELECT SUM((current_price - entry_price) * size_shares) as total FROM positions WHERE is_open=0"
        )
        return float((row or {}).get("total") or 0.0)


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
        existing = _fetchone(con, "SELECT id FROM daily_pnl WHERE date=?", (date,))
        if existing:
            _execute(con,
                """UPDATE daily_pnl SET ending_balance=?, realized_pnl=?,
                   unrealized_pnl=?, num_trades=?, num_wins=?, num_losses=? WHERE date=?""",
                (ending_balance, realized_pnl, unrealized_pnl, num_trades, num_wins, num_losses, date),
            )
        else:
            _execute(con,
                """INSERT INTO daily_pnl
                   (date, starting_balance, ending_balance, realized_pnl,
                    unrealized_pnl, num_trades, num_wins, num_losses)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (date, starting_balance, ending_balance, realized_pnl,
                 unrealized_pnl, num_trades, num_wins, num_losses),
            )


def get_pnl_history(days: int = 30) -> List[Dict]:
    with _conn() as con:
        return _fetchall(con,
            "SELECT * FROM daily_pnl ORDER BY date DESC LIMIT ?", (days,)
        )


def get_today_pnl() -> Optional[Dict]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _conn() as con:
        return _fetchone(con, "SELECT * FROM daily_pnl WHERE date=?", (today,))


def get_initial_balance() -> float:
    with _conn() as con:
        row = _fetchone(con,
            "SELECT starting_balance FROM daily_pnl ORDER BY date ASC LIMIT 1"
        )
        return float((row or {}).get("starting_balance") or 100.0)


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
        existing = _fetchone(con,
            "SELECT id FROM whale_watchlist WHERE proxy_address=?", (proxy_address,)
        )
        if existing:
            _execute(con,
                """UPDATE whale_watchlist SET display_name=?, win_rate=?, total_volume=?,
                   total_profit=?, last_trade_time=?, last_checked=?, rank=?, is_active=1
                   WHERE proxy_address=?""",
                (display_name, win_rate, total_volume, total_profit, last_trade_time,
                 _now(), rank, proxy_address),
            )
        else:
            _execute(con,
                """INSERT INTO whale_watchlist
                   (proxy_address, display_name, win_rate, total_volume, total_profit,
                    last_trade_time, last_checked, rank)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (proxy_address, display_name, win_rate, total_volume, total_profit,
                 last_trade_time, _now(), rank),
            )


def get_active_whales() -> List[Dict]:
    with _conn() as con:
        return _fetchall(con,
            "SELECT * FROM whale_watchlist WHERE is_active=1 ORDER BY rank ASC"
        )


def deactivate_all_whales():
    with _conn() as con:
        _execute(con, "UPDATE whale_watchlist SET is_active=0")


# ── System Events ────────────────────────────────────────────────────

def log_event(
    event_type: str,
    message: str,
    severity: str = "info",
    data: Dict = None,
):
    with _conn() as con:
        _execute(con,
            """INSERT INTO system_events (timestamp, event_type, severity, message, data)
               VALUES (?,?,?,?,?)""",
            (_now(), event_type, severity, message, json.dumps(data) if data else None),
        )


def get_recent_events(limit: int = 100) -> List[Dict]:
    with _conn() as con:
        return _fetchall(con,
            "SELECT * FROM system_events ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
