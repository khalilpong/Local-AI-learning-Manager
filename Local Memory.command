#!/bin/bash
# Local Memory desktop launcher.
# Double-click this file in Finder to start the app and open it in a browser.
set -e
cd "$(dirname "$0")"

if [ -x ".venv/bin/python3" ]; then
  PYTHON=".venv/bin/python3"
else
  PYTHON="python3"
fi

if ! "$PYTHON" -c "import uvicorn" 2>/dev/null; then
  echo "Dependencies missing. Run: $PYTHON -m pip install -r requirements.txt"
  read -r -p "Press Enter to close..."
  exit 1
fi

URL="http://127.0.0.1:8000"
if ! curl -s -o /dev/null --max-time 1 "$URL/api/health"; then
  "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
  SERVER_PID=$!
  trap 'kill "$SERVER_PID" 2>/dev/null' EXIT
  for _ in $(seq 1 20); do
    sleep 0.5
    curl -s -o /dev/null --max-time 1 "$URL/api/health" && break
  done
fi

open "$URL"
echo "Local Memory is running at $URL"
echo "Close this window (or press Ctrl+C) to stop the server."
wait
