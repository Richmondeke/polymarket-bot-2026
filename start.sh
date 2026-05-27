#!/bin/bash
# Start the bot engine in the background
python main.py &

# Start the Flask + SocketIO dashboard in the foreground
gunicorn --worker-class eventlet -w 1 dashboard.app:app --bind 0.0.0.0:$PORT
