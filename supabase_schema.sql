-- ============================================================
-- Polymarket Bot — Supabase PostgreSQL Schema
-- ============================================================
-- HOW TO USE:
-- 1. Go to your Supabase project dashboard
-- 2. Click "SQL Editor" in the left sidebar
-- 3. Paste this entire file and click "Run"
-- 4. All tables will be created. Done.
-- ============================================================

CREATE TABLE IF NOT EXISTS trades (
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
);

CREATE TABLE IF NOT EXISTS positions (
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
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    id               SERIAL PRIMARY KEY,
    date             TEXT    NOT NULL UNIQUE,
    starting_balance REAL,
    ending_balance   REAL,
    realized_pnl     REAL    DEFAULT 0.0,
    unrealized_pnl   REAL    DEFAULT 0.0,
    num_trades       INTEGER DEFAULT 0,
    num_wins         INTEGER DEFAULT 0,
    num_losses       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS whale_watchlist (
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
);

CREATE TABLE IF NOT EXISTS system_events (
    id          SERIAL PRIMARY KEY,
    timestamp   TEXT    NOT NULL,
    event_type  TEXT    NOT NULL,
    severity    TEXT    DEFAULT 'info',
    message     TEXT    NOT NULL,
    data        TEXT
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_trades_market    ON trades(market_id);
CREATE INDEX IF NOT EXISTS idx_trades_status    ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_time      ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_positions_open   ON positions(is_open);
CREATE INDEX IF NOT EXISTS idx_events_time      ON system_events(timestamp);
