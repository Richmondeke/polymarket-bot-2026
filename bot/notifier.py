"""
bot/notifier.py — Email notification system.
Sends real-time SMTP HTML emails for execution alerts, profit cards, and daily summaries.
Runs email sending asynchronously in a background thread to prevent latency.
"""
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
from typing import Dict, Any, List
from loguru import logger

from bot import config
from bot import database as db
from bot.client import clob
from bot.risk_manager import risk


class EmailNotifier:
    """
    Sends email alerts via SMTP.
    Checks config settings; if not defined, logs a warning and fails gracefully.
    """

    def __init__(self):
        self._warned_missing_config = False
        self._triggered_milestones = set()

    def init_milestones(self, current_equity: float):
        """Initialize reached milestones based on current equity on startup."""
        initial = db.get_initial_balance()
        if initial <= 0:
            return
        pnl_pct = ((current_equity - initial) / initial) * 100
        milestones = [10.0, 25.0, 50.0, 100.0, 200.0, 500.0]
        for m in milestones:
            if pnl_pct >= m:
                self._triggered_milestones.add(m)
        logger.info(f"[Notifier] Initialized milestones. Already achieved: {list(self._triggered_milestones)}")

    def check_milestones(self, total_equity: float):
        """Evaluate if portfolio has crossed a new P&L milestone and notify."""
        initial = db.get_initial_balance()
        if initial <= 0:
            return
        pnl_pct = ((total_equity - initial) / initial) * 100
        milestones = [10.0, 25.0, 50.0, 100.0, 200.0, 500.0]
        for m in milestones:
            if pnl_pct >= m and m not in self._triggered_milestones:
                self._triggered_milestones.add(m)
                self.send_milestone_alert(m, pnl_pct, total_equity)

    def send_milestone_alert(self, milestone_pct: float, current_pnl_pct: float, total_equity: float):
        """Send celebratory HTML email for achieving P&L milestones."""
        mode_str = "DRY RUN" if config.DRY_RUN else "LIVE"
        subject = f"[{mode_str}] 🚀 Milestone Reached: +{milestone_pct:.0f}% PnL! Portfolio at ${total_equity:.2f} USDC"
        
        content = f"""
        <div style="text-align: center; margin-bottom: 20px;">
            <span style="font-size: 48px;">🏆</span>
        </div>
        <h2 style="margin-top: 0; font-size: 20px; color: #0f172a; text-align: center;">Congratulations!</h2>
        <p style="font-size: 15px; color: #475569; line-height: 1.6; text-align: center;">
            Your Polymarket trading bot has hit a major performance milestone! The total portfolio equity has grown by <strong>+{current_pnl_pct:.1f}%</strong> since starting.
        </p>

        <div class="card-stat" style="background-color: #f0fdf4; border-color: #bbf7d0; padding: 20px; border-radius: 8px; border: 1px solid; margin: 20px 0; text-align: center;">
            <div style="font-size: 12px; text-transform: uppercase; color: #166534; font-weight: 600;">Milestone Achieved</div>
            <div class="stat-value" style="font-size: 28px; font-weight: 800; color: #15803d; margin-top: 4px;">+{milestone_pct:.0f}% PnL</div>
        </div>

        <div class="grid">
            <div class="grid-row">
                <div class="grid-col grid-col-label">Current Equity</div>
                <div class="grid-col" style="font-weight: 700; color: #0f172a;">${total_equity:.2f} USDC</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Exact PnL %</div>
                <div class="grid-col" style="font-weight: 600; color: #15803d;">+{current_pnl_pct:.1f}%</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Trading Mode</div>
                <div class="grid-col">{mode_str}</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Triggered At</div>
                <div class="grid-col" style="font-size: 13px; color: #64748b;">{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
        </div>
        """
        html_body = self._get_base_template(f"Milestone Hit: +{milestone_pct:.0f}% PnL", content)
        self._send_email_async(subject, html_body)


    def _is_configured(self) -> bool:
        """Check if all required SMTP settings are present."""
        configured = all([
            config.SMTP_SERVER,
            config.SMTP_PORT,
            config.SMTP_USERNAME,
            config.SMTP_PASSWORD,
            config.NOTIFICATION_EMAIL
        ])
        if not configured and not self._warned_missing_config:
            logger.warning(
                "[Notifier] SMTP credentials not fully configured. "
                "Notifications will be skipped. Configure SMTP_SERVER, SMTP_PORT, "
                "SMTP_USERNAME, SMTP_PASSWORD, and NOTIFICATION_EMAIL in your .env."
            )
            self._warned_missing_config = True
        return configured

    def _send_email_sync(self, subject: str, html_body: str):
        """Synchronously connect to SMTP server and send the email."""
        if not self._is_configured():
            return

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"Polymarket Bot <{config.SMTP_USERNAME}>"
            msg['To'] = config.NOTIFICATION_EMAIL
            
            # Record HTML payload
            part = MIMEText(html_body, 'html')
            msg.attach(part)

            # Connect (Port 465 is SSL, others use TLS)
            if config.SMTP_PORT == 465:
                server = smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT, timeout=10)
            else:
                server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT, timeout=10)
                server.ehlo()
                server.starttls()
                server.ehlo()

            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_USERNAME, config.NOTIFICATION_EMAIL, msg.as_string())
            server.quit()
            logger.info(f"[Notifier] Email sent successfully: '{subject}'")
        except Exception as e:
            logger.error(f"[Notifier] Failed to send email: {e}")

    def _send_email_async(self, subject: str, html_body: str):
        """Dispatch email in a daemon thread to prevent blocking trading loop."""
        t = threading.Thread(
            target=self._send_email_sync,
            args=(subject, html_body),
            name="EmailSender",
            daemon=True
        )
        t.start()

    # ── Email Templates ──────────────────────────────────────────────

    def _get_base_template(self, title: str, content_html: str) -> str:
        """Sleek Coinbase-inspired responsive HTML template wrapper."""
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #f4f6f9;
            color: #1e293b;
            margin: 0;
            padding: 0;
            -webkit-font-smoothing: antialiased;
        }}
        .wrapper {{
            width: 100%;
            table-layout: fixed;
            background-color: #f4f6f9;
            padding: 40px 0;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            border: 1px solid #e2e8f0;
        }}
        .header {{
            background-color: #0052ff; /* Coinbase Blue */
            padding: 24px;
            text-align: center;
        }}
        .header h1 {{
            color: #ffffff;
            font-size: 20px;
            font-weight: 700;
            margin: 0;
            letter-spacing: 0.5px;
        }}
        .content {{
            padding: 32px 24px;
        }}
        .footer {{
            background-color: #f8fafc;
            padding: 16px 24px;
            text-align: center;
            border-top: 1px solid #e2e8f0;
            font-size: 12px;
            color: #64748b;
        }}
        .footer a {{
            color: #0052ff;
            text-decoration: none;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .badge-buy {{
            background-color: #ecfdf5;
            color: #059669;
        }}
        .badge-sell {{
            background-color: #fef2f2;
            color: #dc2626;
        }}
        .badge-strategy {{
            background-color: #eff6ff;
            color: #2563eb;
        }}
        .grid {{
            display: table;
            width: 100%;
            margin-top: 20px;
            border-collapse: collapse;
        }}
        .grid-row {{
            display: table-row;
        }}
        .grid-col {{
            display: table-cell;
            padding: 10px;
            border-bottom: 1px solid #f1f5f9;
        }}
        .grid-col-label {{
            font-weight: 600;
            color: #64748b;
            width: 140px;
        }}
        .text-green {{
            color: #059669;
            font-weight: 700;
        }}
        .text-red {{
            color: #dc2626;
            font-weight: 700;
        }}
        .card-stat {{
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 20px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: 700;
            color: #0f172a;
            margin-top: 4px;
        }}
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="container">
            <div class="header">
                <h1>{title}</h1>
            </div>
            <div class="content">
                {content_html}
            </div>
            <div class="footer">
                <p>Polymarket Autonomous Trading Bot</p>
                <p>Monitor status real-time on <a href="http://polymarket.guava.earth">polymarket.guava.earth</a></p>
            </div>
        </div>
    </div>
</body>
</html>
"""

    def send_trade_alert(self, trade: Dict[str, Any]):
        """Format and dispatch a trade filled/placed alert."""
        side = trade.get("side", "BUY").upper()
        shares = trade.get("size_shares", 0.0) or 0.0
        price = trade.get("price", 0.0) or 0.0
        strategy = trade.get("strategy", "unknown")
        market_question = trade.get("market_question") or "Unknown Market"
        total_cost = shares * price

        badge_class = "badge-buy" if side == "BUY" else "badge-sell"
        side_formatted = f"<span class='badge {badge_class}'>{side}</span>"
        strategy_formatted = f"<span class='badge badge-strategy'>{strategy.replace('_', ' ').title()}</span>"
        
        mode_str = "DRY RUN" if trade.get("dry_run", 1) else "LIVE"
        subject = f"[{mode_str}] Trade Executed: {side} {shares:.2f} Shares | {market_question[:30]}..."

        content = f"""
        <h2 style="margin-top: 0; font-size: 18px;">New order filled successfully!</h2>
        <p style="font-size: 14px; color: #475569; line-height: 1.5;">
            The bot has executed a trade in a prediction market based on the active strategy signals.
        </p>
        
        <div class="grid">
            <div class="grid-row">
                <div class="grid-col grid-col-label">Market</div>
                <div class="grid-col" style="font-weight: 600;">{market_question}</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Action / Side</div>
                <div class="grid-col">{side_formatted}</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Strategy</div>
                <div class="grid-col">{strategy_formatted}</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Share Price</div>
                <div class="grid-col">${price:.3f} USDC</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Total Shares</div>
                <div class="grid-col">{shares:.2f} shares</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Value</div>
                <div class="grid-col" style="font-weight: 700; color: #0f172a;">${total_cost:.2f} USDC</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Mode</div>
                <div class="grid-col">{mode_str}</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Time (UTC)</div>
                <div class="grid-col" style="font-size: 13px; color: #64748b;">{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
        </div>
        """
        html_body = self._get_base_template(f"Trade Execution Alert ({mode_str})", content)
        self._send_email_async(subject, html_body)

    def send_profit_alert(
        self,
        market_question: str,
        realized_pnl: float,
        size_usd: float,
        entry_price: float,
        exit_price: float,
        strategy: str
    ):
        """Format and dispatch a profit realized alert."""
        pnl_class = "text-green" if realized_pnl >= 0 else "text-red"
        sign = "+" if realized_pnl >= 0 else ""
        pnl_pct = (realized_pnl / max(size_usd, 0.01)) * 100
        pnl_formatted = f"<span class='{pnl_class}'>{sign}${realized_pnl:.2f} USDC ({sign}{pnl_pct:.1f}%)</span>"
        
        mode_str = "DRY RUN" if config.DRY_RUN else "LIVE"
        subject = f"[{mode_str}] 🎉 Position Closed: {sign}${realized_pnl:.2f} USDC | {market_question[:30]}..."

        strategy_formatted = f"<span class='badge badge-strategy'>{strategy.replace('_', ' ').title()}</span>"

        content = f"""
        <h2 style="margin-top: 0; font-size: 18px; color: #0f172a;">Position Closed Alert</h2>
        <p style="font-size: 14px; color: #475569; line-height: 1.5;">
            An open position has been closed (or resolved), resulting in the following realized outcome.
        </p>

        <div class="card-stat">
            <div style="font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600;">Realized PnL</div>
            <div class="stat-value">{pnl_formatted}</div>
        </div>

        <div class="grid">
            <div class="grid-row">
                <div class="grid-col grid-col-label">Market</div>
                <div class="grid-col" style="font-weight: 600;">{market_question}</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Strategy</div>
                <div class="grid-col">{strategy_formatted}</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Entry Avg Price</div>
                <div class="grid-col">${entry_price:.3f} USDC</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Exit Price</div>
                <div class="grid-col">${exit_price:.3f} USDC</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Position Cost</div>
                <div class="grid-col">${size_usd:.2f} USDC</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Mode</div>
                <div class="grid-col">{mode_str}</div>
            </div>
            <div class="grid-row">
                <div class="grid-col grid-col-label">Closed At</div>
                <div class="grid-col" style="font-size: 13px; color: #64748b;">{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
        </div>
        """
        html_body = self._get_base_template("Position Closed & PnL Alert", content)
        self._send_email_async(subject, html_body)

    def send_daily_report(self):
        """Compile and send daily performance report."""
        if not self._is_configured():
            return

        logger.info("[Notifier] Compiling and sending daily report...")
        try:
            # 1. Update stats for today
            balance = clob.get_usdc_balance()
            risk.record_daily_close(balance)

            # 2. Get today's stats
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_pnl = db.get_today_pnl() or {
                "date": today_str,
                "starting_balance": balance,
                "ending_balance": balance,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "num_trades": 0,
                "num_wins": 0,
                "num_losses": 0
            }

            # Gather more precise numbers
            starting = today_pnl.get("starting_balance") or balance
            ending = today_pnl.get("ending_balance") or balance
            realized = today_pnl.get("realized_pnl") or 0.0
            
            # Fetch unrealized and escrowed details
            escrowed = db.get_escrowed_balance()
            positions_val = db.get_positions_market_value()
            total_equity = ending + escrowed + positions_val

            unrealized = 0.0
            open_positions = db.get_open_positions()
            for p in open_positions:
                unrealized += p.get("unrealized_pnl") or 0.0

            total_trades = today_pnl.get("num_trades") or 0
            wins = today_pnl.get("num_wins") or 0
            losses = today_pnl.get("num_losses") or 0
            win_rate = (wins / max(total_trades, 1)) * 100

            pnl_class = "text-green" if realized >= 0 else "text-red"
            pnl_sign = "+" if realized >= 0 else ""
            pnl_pct = (realized / max(starting, 0.01)) * 100

            unreal_class = "text-green" if unrealized >= 0 else "text-red"
            unreal_sign = "+" if unrealized >= 0 else ""

            mode_str = "DRY RUN" if config.DRY_RUN else "LIVE"
            subject = f"[{mode_str}] Polymarket Bot Daily Report — {today_str} | {pnl_sign}{pnl_pct:.1f}%"

            # Formulate Open Positions table
            positions_rows = ""
            if not open_positions:
                positions_rows = """
                <tr>
                    <td colspan="5" style="padding: 12px; text-align: center; color: #64748b; font-style: italic;">
                        No open positions currently held.
                    </td>
                </tr>
                """
            else:
                for p in open_positions:
                    p_pnl = p.get("unrealized_pnl") or 0.0
                    p_pnl_class = "text-green" if p_pnl >= 0 else "text-red"
                    p_pnl_sign = "+" if p_pnl >= 0 else ""
                    
                    positions_rows += f"""
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #f1f5f9; font-size: 13px;">{p['market_question'][:35]}...</td>
                        <td style="padding: 10px; border-bottom: 1px solid #f1f5f9; font-size: 13px; text-transform: uppercase;">{p['side']}</td>
                        <td style="padding: 10px; border-bottom: 1px solid #f1f5f9; font-size: 13px;">${p['entry_price']:.3f}</td>
                        <td style="padding: 10px; border-bottom: 1px solid #f1f5f9; font-size: 13px;">${p['size_usd']:.2f}</td>
                        <td style="padding: 10px; border-bottom: 1px solid #f1f5f9; font-size: 13px;" class="{p_pnl_class}">{p_pnl_sign}${p_pnl:.2f}</td>
                    </tr>
                    """

            content = f"""
            <h2 style="margin-top: 0; font-size: 18px; color: #0f172a; text-align: center;">Daily Performance Summary</h2>
            <p style="font-size: 14px; color: #64748b; text-align: center; margin-bottom: 30px;">
                Report date: {today_str} UTC | Trading Mode: {mode_str}
            </p>

            <!-- Stats Block -->
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 30px;">
                <tr>
                    <td style="width: 50%; padding: 8px;">
                        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; text-align: center;">
                            <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600;">Daily Realized P&L</div>
                            <div style="font-size: 20px; font-weight: 700; margin-top: 4px;" class="{pnl_class}">{pnl_sign}${realized:.2f} USDC ({pnl_sign}{pnl_pct:.1f}%)</div>
                        </div>
                    </td>
                    <td style="width: 50%; padding: 8px;">
                        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; text-align: center;">
                            <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600;">Total Net Equity</div>
                            <div style="font-size: 20px; font-weight: 700; color: #0052ff; margin-top: 4px;">${total_equity:.2f} USDC</div>
                        </div>
                    </td>
                </tr>
            </table>

            <div class="grid">
                <div class="grid-row">
                    <div class="grid-col grid-col-label">Starting Cash</div>
                    <div class="grid-col" style="font-weight: 600;">${starting:.2f} USDC</div>
                </div>
                <div class="grid-row">
                    <div class="grid-col grid-col-label">Ending Cash</div>
                    <div class="grid-col" style="font-weight: 600;">${ending:.2f} USDC</div>
                </div>
                <div class="grid-row">
                    <div class="grid-col grid-col-label">Escrowed Cash</div>
                    <div class="grid-col">${escrowed:.2f} USDC</div>
                </div>
                <div class="grid-row">
                    <div class="grid-col grid-col-label">Open Position Value</div>
                    <div class="grid-col">${positions_val:.2f} USDC</div>
                </div>
                <div class="grid-row">
                    <div class="grid-col grid-col-label">Unrealized P&L</div>
                    <div class="grid-col class="{unreal_class}">{unreal_sign}${unrealized:.2f} USDC</div>
                </div>
                <div class="grid-row">
                    <div class="grid-col grid-col-label">Trades Executed</div>
                    <div class="grid-col">{total_trades} trades</div>
                </div>
                <div class="grid-row">
                    <div class="grid-col grid-col-label">Daily Win Rate</div>
                    <div class="grid-col" style="font-weight: 600;">{win_rate:.1f}% ({wins} W / {losses} L)</div>
                </div>
            </div>

            <h3 style="margin-top: 32px; font-size: 15px; color: #0f172a; border-bottom: 2px solid #f1f5f9; padding-bottom: 8px;">Active Open Positions ({len(open_positions)})</h3>
            <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                <thead>
                    <tr style="background-color: #f8fafc; text-align: left;">
                        <th style="padding: 10px; border-bottom: 2px solid #e2e8f0; font-size: 12px; color: #64748b; font-weight: 600;">Market</th>
                        <th style="padding: 10px; border-bottom: 2px solid #e2e8f0; font-size: 12px; color: #64748b; font-weight: 600;">Side</th>
                        <th style="padding: 10px; border-bottom: 2px solid #e2e8f0; font-size: 12px; color: #64748b; font-weight: 600;">Entry</th>
                        <th style="padding: 10px; border-bottom: 2px solid #e2e8f0; font-size: 12px; color: #64748b; font-weight: 600;">Size</th>
                        <th style="padding: 10px; border-bottom: 2px solid #e2e8f0; font-size: 12px; color: #64748b; font-weight: 600;">Unrealized P&L</th>
                    </tr>
                </thead>
                <tbody>
                    {positions_rows}
                </tbody>
            </table>
            """
            html_body = self._get_base_template(f"Polymarket Bot Daily Report — {today_str}", content)
            self._send_email_sync(subject, html_body)
        except Exception as e:
            logger.error(f"[Notifier] Failed to compile or send daily report: {e}")


# Singleton Instance
notifier = EmailNotifier()
