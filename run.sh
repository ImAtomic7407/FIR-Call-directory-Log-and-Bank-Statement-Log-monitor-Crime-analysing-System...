#!/bin/bash
# Starts API (:8000) and UI (:5173) from a normal shell. Ctrl+C stops both.
cd "$(dirname "$0")"
(cd backend && source .venv/bin/activate && exec uvicorn main:app --host 0.0.0.0 --port 8000) &
API=$!
(cd frontend && exec npm run dev -- --host 0.0.0.0 --port 5173) &
UI=$!
trap 'kill $API $UI 2>/dev/null' INT TERM EXIT
IP=$(ipconfig getifaddr en0 2>/dev/null)
echo "UI: http://localhost:5173   On LAN: http://$IP:5173   API: http://localhost:8000"
wait
