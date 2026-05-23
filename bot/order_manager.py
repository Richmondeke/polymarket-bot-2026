"""
bot/order_manager.py — Order execution layer.
Translates strategy signals into CLOB API calls.
Handles dry-run mode, order tracking, and kill switch.
"""
import threading
from typing import Optional, Dict, List
from loguru import logger

from bot import config
from bot import database as db
from bot.client import clob, gamma
from bot.risk_manager import risk


class OrderManager:
    """
    Manages all order placement, cancellation, and tracking.
    Is the ONLY module allowed to call clob.place_limit_order().
    """

    def __init__(self):
        self._open_order_ids: Dict[str, str] = {}  # market_id → order_id
        self._lock = threading.Lock()

    # ── Main entry point for copy trades ────────────────────────────

    def place_copy_order(
        self,
        market_id: str,
        market_question: str,
        token_id: str,
        side: str,
        current_price: float,
        size_usd: float,
        whale_address: str = None,
    ) -> Optional[Dict]:
        """
        Mirror a whale's trade with a limit order at/near current market price.
        Places buy orders slightly above best bid to improve fill probability.
        """
        if risk.kill_switch_active:
            logger.warning("[Orders] Kill switch active — skipping order")
            return None

        balance = clob.get_usdc_balance()
        allowed, reason = risk.can_trade(market_id, size_usd, balance)
        if not allowed:
            logger.info(f"[Orders] Trade blocked: {reason}")
            db.log_event("risk", f"Trade blocked ({market_id}): {reason}", severity="warning")
            return None

        # Price: for BUY, place at current price (limit will fill at or better)
        # Add a small buffer above best ask to increase fill probability
        limit_price = round(min(current_price * 1.02, 0.98), 4)  # cap at $0.98
        size_shares = round(size_usd / max(limit_price, 0.01), 2)

        logger.info(
            f"[Orders] {'🟡 DRY RUN' if config.DRY_RUN else '🟢 LIVE'} "
            f"Copy trade: {side} {size_shares:.2f} shares @ ${limit_price:.3f} "
            f"in market '{market_question[:50]}'"
        )

        # Log to DB first
        trade_id = db.log_trade(
            market_id=market_id,
            market_question=market_question,
            side=side,
            price=limit_price,
            size_usd=size_usd,
            size_shares=size_shares,
            strategy="whale_copy",
            whale_address=whale_address,
            status="pending",
            dry_run=config.DRY_RUN,
        )

        # Execute
        resp = clob.place_limit_order(
            token_id=token_id,
            side=side,
            price=limit_price,
            size_shares=size_shares,
        )

        if resp:
            order_id = resp.get("order_id") or resp.get("id") or f"sim-{trade_id}"
            db.update_trade_status(trade_id, "filled" if config.DRY_RUN else "open", limit_price)

            # Record position
            db.upsert_position(
                market_id=market_id,
                market_question=market_question,
                token_id=token_id,
                side=side,
                entry_price=limit_price,
                size_shares=size_shares,
                size_usd=size_usd,
                strategy="whale_copy",
            )

            with self._lock:
                self._open_order_ids[market_id] = order_id

            db.log_event(
                "trade",
                f"{'[DRY]' if config.DRY_RUN else '[LIVE]'} Copy order placed: "
                f"{side} {size_shares:.2f}sh @ ${limit_price:.3f} | {market_question[:40]}",
                severity="info",
                data={"market_id": market_id, "whale": whale_address},
            )
            return resp
        else:
            db.update_trade_status(trade_id, "failed")
            db.log_event("trade", f"Order placement failed: {market_id}", severity="error")
            return None

    # ── Stink bid placement ──────────────────────────────────────────

    def place_stink_bid(
        self,
        market_id: str,
        market_question: str,
        token_id: str,
        best_ask: float,
        size_usd: float,
        discount_pct: float = None,
    ) -> Optional[Dict]:
        """
        Place a deep discount limit BUY order (stink bid).
        Only fills if a whale panic-sells below the discount price.
        """
        if risk.kill_switch_active:
            return None

        discount = (discount_pct or config.STINK_BID_DISCOUNT) / 100.0
        stink_price = round(best_ask * (1.0 - discount), 4)
        stink_price = max(stink_price, 0.01)  # never below 1 cent

        balance = clob.get_usdc_balance()
        allowed, reason = risk.can_trade(market_id, size_usd, balance)
        if not allowed:
            logger.debug(f"[Orders] Stink bid blocked: {reason}")
            return None

        size_shares = round(size_usd / stink_price, 2)

        logger.info(
            f"[Orders] {'🟡 DRY' if config.DRY_RUN else '🟢'} Stink bid: "
            f"BUY {size_shares:.2f} shares @ ${stink_price:.3f} "
            f"({config.STINK_BID_DISCOUNT}% below ${best_ask:.3f}) "
            f"| {market_question[:40]}"
        )

        trade_id = db.log_trade(
            market_id=market_id,
            market_question=market_question,
            side="BUY",
            price=stink_price,
            size_usd=size_usd,
            size_shares=size_shares,
            strategy="stink_bid",
            status="pending",
            dry_run=config.DRY_RUN,
            notes=f"Stink bid: {discount_pct or config.STINK_BID_DISCOUNT}% below ask ${best_ask:.3f}",
        )

        resp = clob.place_limit_order(
            token_id=token_id,
            side="BUY",
            price=stink_price,
            size_shares=size_shares,
        )

        if resp:
            order_id = resp.get("order_id") or resp.get("id") or f"stink-{trade_id}"
            db.update_trade_status(trade_id, "open" if not config.DRY_RUN else "simulated", stink_price)
            with self._lock:
                self._open_order_ids[f"stink_{market_id}"] = order_id

            db.log_event(
                "trade",
                f"Stink bid placed @ ${stink_price:.3f} on {market_question[:40]}",
                data={"market_id": market_id, "discount_pct": discount_pct},
            )

        return resp

    # ── Cancel / Kill Switch ─────────────────────────────────────────

    def cancel_stink_bid(self, market_id: str) -> bool:
        key = f"stink_{market_id}"
        with self._lock:
            order_id = self._open_order_ids.pop(key, None)
        if order_id:
            return clob.cancel_order(order_id)
        return False

    def emergency_cancel_all(self) -> bool:
        """Cancel all open orders immediately (kill switch action)."""
        logger.critical("[Orders] 🔴 EMERGENCY CANCEL ALL ORDERS")
        ok = clob.cancel_all_orders()
        with self._lock:
            self._open_order_ids.clear()
        db.log_event("risk", "Emergency cancel all orders executed", severity="critical")
        return ok

    def get_open_order_count(self) -> int:
        with self._lock:
            return len(self._open_order_ids)

    # ── Order status refresh ─────────────────────────────────────────

    def refresh_order_statuses(self):
        """Poll CLOB for fill status of tracked orders and update DB."""
        if config.DRY_RUN:
            return  # Nothing to poll in dry-run mode
        try:
            live_orders = {o["id"]: o for o in clob.get_open_orders()}
            with self._lock:
                to_remove = []
                for market_key, order_id in self._open_order_ids.items():
                    if order_id not in live_orders:
                        # Order is gone from CLOB — likely filled or expired
                        logger.info(f"[Orders] Order {order_id} filled/expired")
                        to_remove.append(market_key)
                for k in to_remove:
                    del self._open_order_ids[k]
        except Exception as e:
            logger.error(f"[Orders] refresh_order_statuses error: {e}")


# Singleton
orders = OrderManager()
