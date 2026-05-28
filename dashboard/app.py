"""
dashboard/app.py — Flask real-time dashboard.
"""
import os
import threading
import logging
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

from bot import config
from bot import database as db
from bot.risk_manager import risk
from bot.client import clob
from bot.whale_tracker import whale_tracker

app = Flask(__name__)
# Suppress Werkzeug logs for cleaner output
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response


# ── Global Thread-Safe Memory Cache ──────────────────────────────────
CACHED_DATA = {}

def load_initial_cached_data():
    """Populates the cache on startup with fast local SQLite records."""
    global CACHED_DATA
    try:
        trades = db.get_recent_trades(limit=20)
        positions = db.get_open_positions()
        whales = db.get_active_whales()
        
        status = {
            "current_balance": 0.0,
            "escrowed_balance": 0.0,
            "positions_value": 0.0,
            "total_equity": 0.0,
            "daily_pnl_pct": 0.0,
            "drawdown_pct": 0.0,
            "open_positions": len(positions),
            "max_open_positions": config.MAX_OPEN_POSITIONS,
            "total_realized_pnl": 0.0,
            "kill_switch": risk.kill_switch_active,
            "live_trading": config.LIVE_TRADING
        }
        
        # PnL Graph data
        history = db.get_pnl_history(days=14)
        history.reverse() # chronological
        labels = [r['date'] for r in history]
        data = [r['ending_balance'] or r['starting_balance'] for r in history]
        
        if not labels:
            labels = ["Live"]
            data = [0.0]
        else:
            labels.append("Live")
            data.append(data[-1] if data else 0.0)
            
        all_events = db.get_recent_events(limit=80)
        news = [dict(e) for e in all_events if e["event_type"] == "news"]
        arbitrage = [dict(e) for e in all_events if e["event_type"] == "arbitrage_opportunity"]
        system_logs = [dict(e) for e in all_events if e["event_type"] not in ("news", "arbitrage_opportunity")]
        
        CACHED_DATA = {
            "status": status,
            "trades": trades,
            "positions": positions,
            "whales": whales,
            "chart": {'labels': labels, 'data': data},
            "logs": system_logs,
            "news": news,
            "arbitrage": arbitrage
        }
    except Exception as e:
        print(f"[Dashboard] Initial cache load error: {e}")
        CACHED_DATA = {
            "status": {
                "current_balance": 0.0,
                "escrowed_balance": 0.0,
                "positions_value": 0.0,
                "total_equity": 0.0,
                "daily_pnl_pct": 0.0,
                "drawdown_pct": 0.0,
                "open_positions": 0,
                "max_open_positions": 5,
                "total_realized_pnl": 0.0,
                "kill_switch": False,
                "live_trading": config.LIVE_TRADING
            },
            "trades": [],
            "positions": [],
            "whales": [],
            "chart": {'labels': ["Live"], 'data': [0.0]},
            "logs": [],
            "news": [],
            "arbitrage": []
        }

# Pre-populate on boot
load_initial_cached_data()


def background_emitter():
    """Pushes real-time updates via WebSocket and populates the global CACHED_DATA."""
    import time
    last_sync = 0
    while True:
        try:
            now_time = time.time()
            if now_time - last_sync >= 12:
                try:
                    db.sync_live_data("0x71e2a68115542f4CcC394D4953449a0734139F26")
                except Exception as e:
                    print(f"[Dashboard] Sync error: {e}")
                last_sync = now_time

            # 1. Balances & Risk Status (with robust error safety)
            try:
                balance = clob.get_usdc_balance()
            except Exception as e:
                print(f"[Dashboard] Balance fetch error: {e}")
                balance = CACHED_DATA.get("status", {}).get("current_balance", 0.0)

            status = risk.get_status(balance)
            total_equity = status.get("total_equity", balance)
            socketio.emit('status_update', status)
            
            # Check for P&L milestone hits
            try:
                from bot.notifier import notifier
                notifier.check_milestones(total_equity)
            except Exception as e:
                print(f"[Dashboard] Milestone check error: {e}")

            # 2. Recent Fills / Trades
            trades = db.get_recent_trades(limit=20)
            socketio.emit('trades_update', trades)
            
            # 3. Open Positions
            positions = db.get_open_positions()
            socketio.emit('positions_update', positions)

            # 4. Whales
            whales = db.get_active_whales()
            socketio.emit('whales_update', whales)

            # 5. PnL Graph data (plot total equity instead of raw cash)
            history = db.get_pnl_history(days=14)
            history.reverse() # chronological
            labels = [r['date'] for r in history]
            data = [r['ending_balance'] or r['starting_balance'] for r in history]
            
            # Add today's live point
            if labels and labels[-1] == datetime.now(timezone.utc).strftime("%Y-%m-%d"):
                data[-1] = total_equity
            else:
                labels.append("Live")
                data.append(total_equity)
                
            socketio.emit('chart_update', {'labels': labels, 'data': data})

            # 6. News & Arbitrage
            all_events = db.get_recent_events(limit=80)
            news = [dict(e) for e in all_events if e["event_type"] == "news"]
            arbitrage = [dict(e) for e in all_events if e["event_type"] == "arbitrage_opportunity"]
            system_logs = [dict(e) for e in all_events if e["event_type"] not in ("news", "arbitrage_opportunity")]
            
            socketio.emit('news_update', news)
            socketio.emit('arbitrage_update', arbitrage)
            socketio.emit('logs_update', system_logs)
            
            # 7. Update Global Cache atomic reference
            global CACHED_DATA
            CACHED_DATA = {
                "status": status,
                "trades": trades,
                "positions": positions,
                "whales": whales,
                "chart": {'labels': labels, 'data': data},
                "logs": system_logs,
                "news": news,
                "arbitrage": arbitrage
            }
            
        except Exception as e:
            print(f"[Dashboard] Emitter error: {e}")
            
        socketio.sleep(3)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/kill', methods=['POST'])
def kill_switch():
    action = request.json.get('action')
    if action == 'activate':
        risk.activate_kill_switch("Dashboard UI Request")
        from bot.order_manager import orders
        orders.emergency_cancel_all()
        return jsonify({"status": "killed"})
    elif action == 'deactivate':
        risk.deactivate_kill_switch()
        return jsonify({"status": "active"})
    return jsonify({"error": "invalid action"}), 400


@app.route('/api/logs')
def get_logs():
    events = db.get_recent_events(limit=100)
    system_logs = [e for e in events if e["event_type"] not in ("news", "arbitrage_opportunity")]
    return jsonify(system_logs)


@app.route('/api/data')
def get_dashboard_data():
    try:
        global CACHED_DATA
        if not CACHED_DATA:
            load_initial_cached_data()
        return jsonify(CACHED_DATA)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def start_dashboard():
    print(f"[Dashboard] Starting on http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}")
    socketio.start_background_task(background_emitter)
    socketio.run(app, host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT, debug=False, use_reloader=False)
