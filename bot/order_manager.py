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

    def _handle_post_execution(
        self,
        trade_id: int,
        market_id: str,
        market_question: str,
        token_id: str,
        side: str,
        limit_price: float,
        size_shares: float,
        size_usd: float,
        strategy: str,
        status: str,
        whale_address: str = None
    ):
        """Update DB status, upsert or close positions, and send email alerts."""
        db.update_trade_status(trade_id, status, limit_price)

        from bot.notifier import notifier

        # Check if we have an open position to resolve or sell
        if side.upper() == "SELL":
            open_positions = db.get_open_positions()
            existing = next((p for p in open_positions if p["market_id"] == market_id), None)
            if existing:
                entry_price = existing["entry_price"]
                realized_pnl = (limit_price - entry_price) * size_shares
                db.close_position(market_id, exit_price=limit_price)
                logger.info(f"[Orders] Closed position in '{market_question}' realizing PnL: ${realized_pnl:.2f}")
                notifier.send_profit_alert(
                    market_question=market_question,
                    realized_pnl=realized_pnl,
                    size_usd=existing["size_usd"],
                    entry_price=entry_price,
                    exit_price=limit_price,
                    strategy=strategy
                )
            else:
                db.close_position(market_id, exit_price=limit_price)
        else:
            db.upsert_position(
                market_id=market_id,
                market_question=market_question,
                token_id=token_id,
                side=side,
                entry_price=limit_price,
                size_shares=size_shares,
                size_usd=size_usd,
                strategy=strategy,
            )
            
            trade_data = {
                "side": side,
                "size_shares": size_shares,
                "price": limit_price,
                "strategy": strategy,
                "market_question": market_question,
                "dry_run": config.DRY_RUN
            }
            notifier.send_trade_alert(trade_data)

        # Trigger milestone check on any trade action
        try:
            balance = clob.get_usdc_balance()
            status_data = risk.get_status(balance)
            notifier.check_milestones(status_data.get("total_equity", balance))
        except Exception as e:
            logger.error(f"[Orders] Milestone check error: {e}")


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
            self._handle_post_execution(
                trade_id=trade_id,
                market_id=market_id,
                market_question=market_question,
                token_id=token_id,
                side=side,
                limit_price=limit_price,
                size_shares=size_shares,
                size_usd=size_usd,
                strategy="whale_copy",
                status="filled" if config.DRY_RUN else "open",
                whale_address=whale_address
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

    # ── Main entry point for sentiment trades ───────────────────────

    def place_sentiment_trade(
        self,
        market_id: str,
        market_question: str,
        token_id: str,
        side: str,  # BUY or SELL
        outcome: str,  # Yes or No
        current_price: float,
        size_usd: float,
        ai_prob: float,
    ) -> Optional[Dict]:
        """
        Execute a trade based on AI news sentiment arbitrage.
        """
        if risk.kill_switch_active:
            logger.warning("[Orders] Kill switch active — skipping order")
            return None

        balance = clob.get_usdc_balance()
        allowed, reason = risk.can_trade(market_id, size_usd, balance)
        if not allowed:
            logger.info(f"[Orders] Sentiment trade blocked: {reason}")
            db.log_event("risk", f"Sentiment trade blocked ({market_id}): {reason}", severity="warning")
            return None

        limit_price = round(min(current_price * 1.02, 0.98), 4)
        size_shares = round(size_usd / max(limit_price, 0.01), 2)
        question_with_outcome = f"{market_question} ({outcome.upper()})"

        logger.info(
            f"[Orders] {'🟡 DRY RUN' if config.DRY_RUN else '🟢 LIVE'} "
            f"Sentiment trade: {side} {size_shares:.2f} shares @ ${limit_price:.3f} "
            f"in market '{question_with_outcome[:50]}'"
        )

        trade_id = db.log_trade(
            market_id=market_id,
            market_question=question_with_outcome,
            side=side,
            price=limit_price,
            size_usd=size_usd,
            size_shares=size_shares,
            strategy="news_sentiment",
            status="pending",
            dry_run=config.DRY_RUN,
            notes=f"AI Probability: {ai_prob * 100:.1f}%",
        )

        resp = clob.place_limit_order(
            token_id=token_id,
            side=side,
            price=limit_price,
            size_shares=size_shares,
        )

        if resp:
            order_id = resp.get("order_id") or resp.get("id") or f"sent-{trade_id}"
            self._handle_post_execution(
                trade_id=trade_id,
                market_id=market_id,
                market_question=question_with_outcome,
                token_id=token_id,
                side=side,
                limit_price=limit_price,
                size_shares=size_shares,
                size_usd=size_usd,
                strategy="news_sentiment",
                status="filled" if config.DRY_RUN else "open"
            )

            with self._lock:
                self._open_order_ids[market_id] = order_id

            db.log_event(
                "trade",
                f"{'[DRY]' if config.DRY_RUN else '[LIVE]'} Sentiment order placed: "
                f"{side} {outcome.upper()} {size_shares:.2f}sh @ ${limit_price:.3f} | {market_question[:40]}",
                severity="info",
                data={"market_id": market_id, "ai_prob": ai_prob},
            )
            return resp
        else:
            db.update_trade_status(trade_id, "failed")
            db.log_event("trade", f"Sentiment order placement failed: {market_id}", severity="error")
            return None

    # ── Main entry point for arbitrage basket trades ────────────────

    def place_arbitrage_basket(
        self,
        event_id: str,
        event_title: str,
        legs: List[Dict],  # [{"market_id", "market_question", "token_id", "outcome", "price", "shares"}]
        basket_type: str,  # NO_BASKET or YES_BASKET
        total_cost_usd: float,
    ) -> bool:
        """
        Place limit buy orders on all legs of an arbitrage basket.
        """
        if risk.kill_switch_active:
            logger.warning("[Orders] Kill switch active — skipping arbitrage basket")
            return False

        balance = clob.get_usdc_balance()
        # Perform check on total cost
        allowed, reason = risk.can_trade(f"arb_{event_id}", total_cost_usd, balance)
        if not allowed:
            logger.info(f"[Orders] Arbitrage basket blocked: {reason}")
            db.log_event("risk", f"Arbitrage basket blocked ({event_id}): {reason}", severity="warning")
            return False

        logger.info(
            f"[Orders] {'🟡 DRY RUN' if config.DRY_RUN else '🟢 LIVE'} "
            f"Arbitrage basket ({basket_type}) for event '{event_title[:40]}': "
            f"placing {len(legs)} orders, total cost ~${total_cost_usd:.2f}"
        )

        succeeded_legs = []
        for leg in legs:
            m_id = leg["market_id"]
            question = leg["market_question"]
            t_id = leg["token_id"]
            outcome = leg["outcome"]
            price = leg["price"]
            shares = leg["shares"]
            
            leg_cost = price * shares
            question_with_outcome = f"{question} ({outcome.upper()})"

            # Log leg trade as pending
            trade_id = db.log_trade(
                market_id=m_id,
                market_question=question_with_outcome,
                side="BUY",
                price=price,
                size_usd=leg_cost,
                size_shares=shares,
                strategy="arbitrage",
                status="pending",
                dry_run=config.DRY_RUN,
                notes=f"Arbitrage Event ID: {event_id} | Basket: {basket_type}",
            )

            # Place order
            resp = clob.place_limit_order(
                token_id=t_id,
                side="BUY",
                price=price,
                size_shares=shares,
            )

            if resp:
                self._handle_post_execution(
                    trade_id=trade_id,
                    market_id=m_id,
                    market_question=question_with_outcome,
                    token_id=t_id,
                    side="BUY",
                    limit_price=price,
                    size_shares=shares,
                    size_usd=leg_cost,
                    strategy="arbitrage",
                    status="filled" if config.DRY_RUN else "open"
                )
                order_id = resp.get("order_id") or resp.get("id") or f"arb-{trade_id}"
                with self._lock:
                    self._open_order_ids[m_id] = order_id
                succeeded_legs.append(leg)
            else:
                db.update_trade_status(trade_id, "failed")
                logger.error(f"[Orders] Arbitrage leg order failed: {m_id} {outcome}")
                # In live mode, we would want to cancel already placed legs!
                # For simplicity in V1, we log the error. In dry-run, it always succeeds.

        if len(succeeded_legs) == len(legs):
            db.log_event(
                "trade",
                f"Arbitrage basket placed: {basket_type} on '{event_title[:40]}' | Net profit margin estimated",
                severity="info",
                data={"event_id": event_id, "legs": len(legs)},
            )
            return True
        return False

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
            self._handle_post_execution(
                trade_id=trade_id,
                market_id=market_id,
                market_question=market_question,
                token_id=token_id,
                side="BUY",
                limit_price=stink_price,
                size_shares=size_shares,
                size_usd=size_usd,
                strategy="stink_bid",
                status="simulated" if config.DRY_RUN else "open"
            )
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
            db.update_trade_status_by_market(market_id, "cancelled")
            return clob.cancel_order(order_id)
        return False

    def emergency_cancel_all(self) -> bool:
        """Cancel all open orders immediately (kill switch action)."""
        logger.critical("[Orders] 🔴 EMERGENCY CANCEL ALL ORDERS")
        ok = clob.cancel_all_orders()
        with self._lock:
            self._open_order_ids.clear()
        
        # Update all open/simulated trades in DB to cancelled
        with db._conn() as con:
            con.execute("UPDATE trades SET status='cancelled' WHERE status IN ('open', 'simulated')")
            
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
