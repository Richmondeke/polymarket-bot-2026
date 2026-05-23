"""
dashboard/app.py — Flask real-time dashboard.
"""
import os
import threading
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
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

def background_emitter():
    """Pushes real-time updates to the dashboard via WebSocket."""
    while True:
        try:
            # 1. Balances & Risk Status
            balance = clob.get_usdc_balance()
            status = risk.get_status(balance)
            total_equity = status.get("total_equity", balance)
            socketio.emit('status_update', status)
            
            # Check for P&L milestone hits
            from bot.notifier import notifier
            notifier.check_milestones(total_equity)

            
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
        balance = clob.get_usdc_balance()
        status = risk.get_status(balance)
        total_equity = status.get("total_equity", balance)
        trades = db.get_recent_trades(limit=20)
        positions = db.get_open_positions()
        whales = db.get_active_whales()
        
        # PnL Graph data
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
            
        all_events = db.get_recent_events(limit=80)
        news = [dict(e) for e in all_events if e["event_type"] == "news"]
        arbitrage = [dict(e) for e in all_events if e["event_type"] == "arbitrage_opportunity"]
        system_logs = [dict(e) for e in all_events if e["event_type"] not in ("news", "arbitrage_opportunity")]
        
        return jsonify({
            "status": status,
            "trades": trades,
            "positions": positions,
            "whales": whales,
            "chart": {'labels': labels, 'data': data},
            "logs": system_logs,
            "news": news,
            "arbitrage": arbitrage
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def start_dashboard():
    print(f"[Dashboard] Starting on http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}")
    socketio.start_background_task(background_emitter)
    socketio.run(app, host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT, debug=False, use_reloader=False)

