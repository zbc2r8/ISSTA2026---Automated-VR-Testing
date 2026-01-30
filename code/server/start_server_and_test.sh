#!/bin/bash
# Script to start the server and run tests

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "=================================="
echo "War App Model Server Startup"
echo "=================================="

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    exit 1
fi

# Check if required packages are installed
echo "Checking dependencies..."
python3 -c "import flask, joblib, numpy, pandas, requests" 2>/dev/null || {
    echo "❌ Missing required packages. Installing..."
    pip install -r requirements.txt 2>/dev/null || {
        echo "⚠️ Could not install via pip. Please install manually:"
        echo "   pip install flask flask-cors joblib numpy pandas scikit-learn requests"
        exit 1
    }
}

# Check optional flask_cors (not critical)
python3 -c "import flask_cors" 2>/dev/null || {
    echo "⚠️  flask_cors not installed (optional, for CORS support). Server will work without it."
    echo "   To install: pip install flask-cors"
}

# Check if model files exist
if [ ! -f "saved_model/model.joblib" ]; then
    echo "❌ Model file not found: saved_model/model.joblib"
    exit 1
fi

if [ ! -f "saved_model/meta.json" ]; then
    echo "❌ Metadata file not found: saved_model/meta.json"
    exit 1
fi

if [ ! -f "gameover_war_data_5fps_p1_01.csv" ]; then
    echo "❌ Test data file not found: gameover_war_data_5fps_p1_01.csv"
    exit 1
fi

echo "✅ All dependencies and files found"
echo ""

# Start server in background
echo "Starting server on http://localhost:5000..."
python3 model_server.py --port 5000 > server.log 2>&1 &
SERVER_PID=$!

echo "Server started with PID: $SERVER_PID"
echo "Logs are being written to server.log"

# Wait for server to be ready
echo "Waiting for server to be ready..."
for i in {1..10}; do
    sleep 2
    if curl -s http://localhost:5000/health > /dev/null 2>&1; then
        echo "✅ Server is ready!"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "❌ Server failed to start"
        kill $SERVER_PID 2>/dev/null || true
        exit 1
    fi
done

echo ""
echo "Running tests with real data..."
echo ""

# Run tests
python3 test_with_real_data.py
TEST_EXIT_CODE=$?

# Stop server
echo ""
echo "Stopping server (PID: $SERVER_PID)..."
kill $SERVER_PID 2>/dev/null || true
wait $SERVER_PID 2>/dev/null || true

echo ""
echo "Server stopped."
echo "Check server.log for server output."

exit $TEST_EXIT_CODE
