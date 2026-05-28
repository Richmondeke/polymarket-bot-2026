"""
bot/risk_manager.py — Risk controls and failsafe system.
Checks every trade before execution. Enforces:
  - No duplicate positions in the same market
  - Daily stop-loss limit (5% default)
  - Total portfolio drawdown limit (15% default)
  - Fractional Kelly position sizing
  - Max open position count
"""
import threading
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from bot import config
from bot import database as db


class RiskManager:
    """
    Central risk controller. All trading decisions must pass through here.
    Thread-safe singleton.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._kill_switch = False
        self._daily_start_balance: Optional[float] = None

    # ── Kill Switch ──────────────────────────────────────────────────

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch

    def activate_kill_switch(self, reason: str = "Manual"):
        with self._lock:
            self._kill_switch = True
        logger.critical(f"[Risk] 🔴 KILL SWITCH ACTIVATED — {reason}")
        db.log_event("risk", f"Kill switch activated: {reason}", severity="critical")

    def deactivate_kill_switch(self):
        with self._lock:
            self._kill_switch = False
        logger.info("[Risk] 🟢 Kill switch deactivated")
        db.log_event("risk", "Kill switch deactivated", severity="info")

    # ── Pre-Trade Checks ─────────────────────────────────────────────

    def can_trade(
        self,
        market_id: str,
        size_usd: float,
        current_balance: float,
        side: str = "BUY",
    ) -> tuple[bool, str]:
        """
        Master pre-trade check. Returns (allowed, reason).
        ALL checks must pass for a trade to proceed.
        """
        # 1. Kill switch
        if self._kill_switch:
            return False, "Kill switch is active"

        # 2. Duplicate position guard
        if side.upper() == "BUY" and db.position_exists(market_id):
            return False, f"Position already open in market {market_id}"

        # 3. Max open positions
        if side.upper() == "BUY":
            open_positions = db.get_open_positions()
            if len(open_positions) >= config.MAX_OPEN_POSITIONS:
                return False, f"Max open positions reached ({config.MAX_OPEN_POSITIONS})"

        # 4. Insufficient balance (must have actual cash)
        if side.upper() == "BUY" and size_usd > current_balance * 0.95:
            return False, f"Insufficient cash: ${current_balance:.2f} for ${size_usd:.2f} trade"

        # Calculate Total Equity for risk limits
        escrowed = db.get_escrowed_balance()
        positions_val = db.get_positions_market_value()
        total_equity = current_balance + escrowed + positions_val

        # 5. Daily stop-loss (uses total equity)
        daily_ok, daily_msg = self._check_daily_stop_loss(total_equity)
        if not daily_ok:
            return False, daily_msg

        # 6. Max drawdown (uses total equity)
        drawdown_ok, drawdown_msg = self._check_max_drawdown(total_equity)
        if not drawdown_ok:
            return False, drawdown_msg

        return True, "OK"

    def _check_daily_stop_loss(self, current_balance: float) -> tuple[bool, str]:
        """Halt if today's P&L has dropped more than the daily stop-loss %."""
        if self._daily_start_balance is None:
            return True, "OK"

        daily_pnl_pct = (
            (current_balance - self._daily_start_balance) / self._daily_start_balance * 100
        )
        if daily_pnl_pct <= -config.DAILY_STOP_LOSS_PCT:
            msg = (
                f"Daily stop-loss triggered: {daily_pnl_pct:.1f}% "
                f"(limit: -{config.DAILY_STOP_LOSS_PCT}%)"
            )
            logger.warning(f"[Risk] ⚠️  {msg}")
            db.log_event("risk", msg, severity="warning")
            return False, msg
        return True, "OK"

    def _check_max_drawdown(self, current_balance: float) -> tuple[bool, str]:
        """Halt if total portfolio has declined more than max drawdown %."""
        # Use starting balance from DB history
        history = db.get_pnl_history(days=90)
        if not history:
            return True, "OK"

        # Find the highest balance recorded (all-time peak)
        fallback_peak = self._daily_start_balance or current_balance
        peak = max(
            (r.get("ending_balance") or r.get("starting_balance") or fallback_peak)
            for r in history
        )
        if peak <= 0:
            return True, "OK"

        drawdown_pct = (peak - current_balance) / peak * 100
        if drawdown_pct >= config.MAX_DRAWDOWN_PCT:
            msg = (
                f"Max drawdown exceeded: {drawdown_pct:.1f}% from peak ${peak:.2f} "
                f"(limit: {config.MAX_DRAWDOWN_PCT}%)"
            )
            logger.critical(f"[Risk] 🔴 {msg}")
            self.activate_kill_switch(msg)
            return False, msg
        return True, "OK"

    # ── Position Sizing ──────────────────────────────────────────────

    def calculate_position_size(
        self,
        win_probability: float,
        current_balance: float,
        odds: float = None,
    ) -> float:
        """
        Fractional Kelly Criterion position sizing.
        Returns size in USD, capped at MAX_POSITION_SIZE_USD.

        Kelly formula: f* = (bp - q) / b
          b = net odds (1/price - 1 for binary market)
          p = estimated win probability
          q = 1 - p
        """
        if not odds:
            # Assume market price ≈ implied probability
            odds = (1.0 / max(win_probability, 0.01)) - 1.0

        p = win_probability
        q = 1.0 - p
        b = odds

        if b <= 0:
            return config.POSITION_SIZE_USD

        kelly_fraction = (b * p - q) / b
        kelly_fraction = max(0, kelly_fraction)

        # Apply fractional Kelly (reduce variance)
        fractional_kelly = kelly_fraction * config.KELLY_FRACTION
        size_usd = fractional_kelly * current_balance

        # Apply limits
        size_usd = max(size_usd, config.POSITION_SIZE_USD)      # minimum
        size_usd = min(size_usd, config.MAX_POSITION_SIZE_USD)  # maximum

        logger.debug(
            f"[Risk] Kelly: p={p:.2f}, odds={b:.2f}, "
            f"f*={kelly_fraction:.3f}, fractional={fractional_kelly:.3f}, "
            f"size=${size_usd:.2f}"
        )
        return round(size_usd, 2)

    # ── Daily Balance Tracking ───────────────────────────────────────

    def set_daily_start_balance(self, balance: float):
        """Call once at the start of each trading day."""
        with self._lock:
            self._daily_start_balance = balance
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        db.upsert_daily_pnl(date=today, starting_balance=balance)
        logger.info(f"[Risk] Daily start balance set: ${balance:.2f}")

    def record_daily_close(self, current_balance: float):
        """Call at end of day or on shutdown to record final balance."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_pnl = db.get_today_pnl() or {}
        realized = current_balance - (self._daily_start_balance or current_balance)

        trades = db.get_recent_trades(limit=500)
        today_str = today
        today_trades = [t for t in trades if t["timestamp"].startswith(today_str)]
        wins = sum(1 for t in today_trades if (t.get("fill_price") or 0) > (t.get("price") or 0))

        db.upsert_daily_pnl(
            date=today,
            starting_balance=self._daily_start_balance,
            ending_balance=current_balance,
            realized_pnl=realized,
            num_trades=len(today_trades),
            num_wins=wins,
            num_losses=max(0, len(today_trades) - wins),
        )

    # ── Reporting ────────────────────────────────────────────────────

    def get_status(self, current_balance: float) -> dict:
        """Return a snapshot of current risk metrics for the dashboard."""
        escrowed = db.get_escrowed_balance()
        positions_val = db.get_positions_market_value()
        total_equity = current_balance + escrowed + positions_val

        history = db.get_pnl_history(days=90)
        fallback_peak = self._daily_start_balance or total_equity
        peak = max(
            (r.get("ending_balance") or fallback_peak for r in history),
            default=fallback_peak,
        )
        peak = max(peak, self._daily_start_balance or total_equity, total_equity)
        drawdown_pct = (peak - total_equity) / max(peak, 1.0) * 100

        daily_pnl_pct = 0.0
        if self._daily_start_balance and self._daily_start_balance > 0:
            daily_pnl_pct = (
                (total_equity - self._daily_start_balance)
                / self._daily_start_balance * 100
            )

        return {
            "kill_switch": self._kill_switch,
            "dry_run": config.DRY_RUN,
            "live_trading": config.LIVE_TRADING,
            "current_balance": current_balance,
            "escrowed_balance": round(escrowed, 2),
            "positions_value": round(positions_val, 2),
            "total_equity": round(total_equity, 2),
            "daily_start_balance": self._daily_start_balance,
            "daily_pnl_pct": round(daily_pnl_pct, 2),
            "daily_stop_loss_pct": config.DAILY_STOP_LOSS_PCT,
            "drawdown_pct": round(drawdown_pct, 2),
            "max_drawdown_pct": config.MAX_DRAWDOWN_PCT,
            "open_positions": len(db.get_open_positions()),
            "max_open_positions": config.MAX_OPEN_POSITIONS,
            "total_realized_pnl": round(db.get_total_realized_pnl(), 2),
        }



# Singleton instance
risk = RiskManager()
