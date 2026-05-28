"""
bot/firebase_db.py — Firestore persistence adapter.
Used automatically when FIREBASE_PROJECT_ID env var is set.
Mirrors every function signature in database.py exactly.
Collections: trades, positions, daily_pnl, whale_watchlist, system_events
"""
import os
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from loguru import logger

import firebase_admin
from firebase_admin import credentials, firestore

# ── Init ─────────────────────────────────────────────────────────────
_app = None
_db  = None

def _get_db():
    global _app, _db
    if _db is None:
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        if not _app:
            # In GitHub Actions: uses GOOGLE_APPLICATION_CREDENTIALS env var or ADC
            # Locally: uses firebase CLI auth (application default credentials)
            try:
                _app = firebase_admin.get_app()
            except ValueError:
                _app = firebase_admin.initialize_app(options={"projectId": project_id})
        _db = firestore.client()
        logger.info(f"[DB] Firestore connected → project: {project_id}")
    return _db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _col(name: str):
    """Return a Firestore collection reference."""
    return _get_db().collection(name)


# ── Schema init (no-op for Firestore — collections auto-create) ──────

def init_db():
    _get_db()  # just ensures connection
    logger.info("[DB] Firestore ready — collections auto-created on first write")


# ── Trades ───────────────────────────────────────────────────────────

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
) -> str:
    doc = {
        "timestamp": _now(),
        "market_id": market_id,
        "market_question": market_question,
        "side": side.upper(),
        "price": price,
        "size_usd": size_usd,
        "size_shares": size_shares,
        "order_id": order_id,
        "strategy": strategy,
        "whale_address": whale_address,
        "status": status,
        "dry_run": int(dry_run),
        "notes": notes,
        "fill_price": None,
        "fill_time": None,
    }
    ref = _col("trades").add(doc)
    return ref[1].id


def update_trade_status(trade_id: str, status: str, fill_price: float = None):
    update = {"status": status}
    if fill_price is not None:
        update["fill_price"] = fill_price
        update["fill_time"] = _now()
    _col("trades").document(str(trade_id)).update(update)


def update_trade_status_by_market(market_id: str, status: str):
    refs = _col("trades").where("market_id", "==", market_id)\
                         .where("status", "in", ["open", "simulated"]).stream()
    for doc in refs:
        doc.reference.update({"status": status})


def get_escrowed_balance() -> float:
    docs = _col("trades").where("status", "in", ["open", "simulated"]).stream()
    total = 0.0
    for d in docs:
        data = d.to_dict()
        total += (data.get("price") or 0) * (data.get("size_shares") or 0)
    return total


def get_positions_market_value() -> float:
    docs = _col("positions").where("is_open", "==", 1).stream()
    val = 0.0
    for d in docs:
        data = d.to_dict()
        p = data.get("current_price") or data.get("entry_price") or 0
        val += p * (data.get("size_shares") or 0)
    return val


def get_recent_trades(limit: int = 50) -> List[Dict]:
    docs = _col("trades").order_by("timestamp", direction=firestore.Query.DESCENDING)\
                         .limit(limit).stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]


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
    ref = _col("positions").document(market_id)
    snap = ref.get()
    if snap.exists and snap.to_dict().get("is_open") == 1:
        ref.update({"current_price": entry_price, "updated_at": _now()})
    else:
        ref.set({
            "market_id": market_id,
            "market_question": market_question,
            "token_id": token_id,
            "side": side.upper(),
            "entry_price": entry_price,
            "current_price": entry_price,
            "size_shares": size_shares,
            "size_usd": size_usd,
            "unrealized_pnl": 0.0,
            "strategy": strategy,
            "end_date": end_date,
            "opened_at": _now(),
            "updated_at": _now(),
            "is_open": 1,
        })


def close_position(market_id: str, exit_price: float = None):
    _col("positions").document(market_id).update({
        "is_open": 0,
        "updated_at": _now(),
        "current_price": exit_price,
    })


def update_position_prices(prices: Dict[str, float]):
    for market_id, price in prices.items():
        ref = _col("positions").document(market_id)
        snap = ref.get()
        if snap.exists:
            data = snap.to_dict()
            if data.get("is_open") == 1:
                upnl = (price - data["entry_price"]) * data["size_shares"]
                ref.update({"current_price": price, "unrealized_pnl": upnl, "updated_at": _now()})


def get_open_positions() -> List[Dict]:
    docs = _col("positions").where("is_open", "==", 1)\
                            .order_by("opened_at", direction=firestore.Query.DESCENDING).stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]


def position_exists(market_id: str) -> bool:
    snap = _col("positions").document(market_id).get()
    return snap.exists and snap.to_dict().get("is_open") == 1


def get_total_realized_pnl() -> float:
    docs = _col("positions").where("is_open", "==", 0).stream()
    total = 0.0
    for d in docs:
        data = d.to_dict()
        cp = data.get("current_price") or data.get("entry_price") or 0
        total += (cp - data["entry_price"]) * data["size_shares"]
    return total


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
    doc = {
        "date": date,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "num_trades": num_trades,
        "num_wins": num_wins,
        "num_losses": num_losses,
    }
    if starting_balance is not None:
        doc["starting_balance"] = starting_balance
    if ending_balance is not None:
        doc["ending_balance"] = ending_balance

    _col("daily_pnl").document(date).set(doc, merge=True)


def get_pnl_history(days: int = 30) -> List[Dict]:
    docs = _col("daily_pnl").order_by("date", direction=firestore.Query.DESCENDING)\
                            .limit(days).stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]


def get_today_pnl() -> Optional[Dict]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snap = _col("daily_pnl").document(today).get()
    return snap.to_dict() if snap.exists else None


def get_initial_balance() -> float:
    docs = _col("daily_pnl").order_by("date").limit(1).stream()
    for d in docs:
        return float(d.to_dict().get("starting_balance") or 100.0)
    return 100.0


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
    _col("whale_watchlist").document(proxy_address).set({
        "proxy_address": proxy_address,
        "display_name": display_name,
        "win_rate": win_rate,
        "total_volume": total_volume,
        "total_profit": total_profit,
        "last_trade_time": last_trade_time,
        "last_checked": _now(),
        "is_active": 1,
        "rank": rank,
    }, merge=True)


def get_active_whales() -> List[Dict]:
    docs = _col("whale_watchlist").where("is_active", "==", 1)\
                                  .order_by("rank").stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]


def deactivate_all_whales():
    for d in _col("whale_watchlist").stream():
        d.reference.update({"is_active": 0})


# ── System Events ────────────────────────────────────────────────────

def log_event(
    event_type: str,
    message: str,
    severity: str = "info",
    data: Dict = None,
):
    _col("system_events").add({
        "timestamp": _now(),
        "event_type": event_type,
        "severity": severity,
        "message": message,
        "data": json.dumps(data) if data else None,
    })


def get_recent_events(limit: int = 100) -> List[Dict]:
    docs = _col("system_events").order_by("timestamp", direction=firestore.Query.DESCENDING)\
                                .limit(limit).stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]
