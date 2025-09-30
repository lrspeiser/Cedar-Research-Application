#!/bin/bash
# restart_server.sh - Clean restart of the uvicorn server

set -e

cd "$(dirname "$0")"

PORT=8000

echo "🔍 Checking for running uvicorn processes..."

# Kill any existing uvicorn processes
if pgrep -f "uvicorn main:app" > /dev/null; then
    echo "🛑 Stopping existing server..."
    pkill -9 -f "uvicorn main:app" || true
    sleep 2
    echo "✅ Server stopped"
else
    echo "ℹ️  No existing server found"
fi

# Verify all processes are gone
if pgrep -f "uvicorn main:app" > /dev/null; then
    echo "⚠️  Warning: Some processes still running, force killing..."
    pkill -9 -f "uvicorn main:app" || true
    sleep 1
fi

# Ensure the desired port is free before starting
echo "🔒 Ensuring port $PORT is free..."
if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
    echo "🧹 Freeing port $PORT..."
    PIDS_ON_PORT=$(lsof -nP -t -iTCP:$PORT -sTCP:LISTEN | tr '\n' ' ')
    if [ -n "$PIDS_ON_PORT" ]; then
        kill $PIDS_ON_PORT || true
        sleep 1
        # Force kill if still listening
        if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
            kill -9 $PIDS_ON_PORT || true
            sleep 1
        fi
        echo "✅ Port $PORT is now free"
    fi
else
    echo "ℹ️  Port $PORT is already free"
fi

echo "🚀 Starting server..."

# Start server in background
nohup uvicorn main:app --reload --host 127.0.0.1 --port $PORT > server.log 2>&1 &
SERVER_PID=$!

echo "⏳ Waiting for server to start..."
sleep 3

# Check if server started successfully
if ps -p $SERVER_PID > /dev/null; then
    echo "✅ Server started successfully!"
    echo "📋 Process ID: $SERVER_PID"
    echo "🌐 Server URL: http://127.0.0.1:8000"
    echo "📝 Logs: tail -f server.log"
    echo ""
    echo "Recent log output:"
    tail -10 server.log
else
    echo "❌ Server failed to start. Check server.log for details:"
    tail -20 server.log
    exit 1
fi
