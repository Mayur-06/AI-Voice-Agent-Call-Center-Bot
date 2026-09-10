#!/bin/bash
# Start the backend and the frontend dev server for local testing.
#   ./start-local.sh          start both
#   ./start-local.sh stop     stop both
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$ROOT/logs"; mkdir -p "$LOGS"

stop() {
  for p in $(pgrep -f 'uvicorn app\.main' 2>/dev/null); do kill "$p" 2>/dev/null; done
  for p in $(pgrep -f 'vite.*AI-Voice-Agent-App|AI-Voice-Agent-App.*vite' 2>/dev/null); do kill "$p" 2>/dev/null; done
  # vite also shows up as the node process serving port 5173
  fuser -k 5173/tcp 2>/dev/null
  echo "stopped"
}

[ "${1:-}" = "stop" ] && { stop; exit 0; }

stop >/dev/null 2>&1; sleep 1

echo "starting backend  -> http://localhost:8001"
( cd "$ROOT/backend" && nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 > "$LOGS/backend-local.log" 2>&1 & )

echo "starting frontend -> http://localhost:5173"
( cd "$ROOT/AI-Voice-Agent-App" && nohup npm run dev -- --port 5173 --host 127.0.0.1 > "$LOGS/frontend-local.log" 2>&1 & )

printf "waiting for backend"
for i in $(seq 1 40); do
  curl -sf -m 2 http://127.0.0.1:8001/api/health >/dev/null 2>&1 && { echo " ready"; break; }
  printf "."; sleep 1
done
printf "waiting for frontend"
for i in $(seq 1 40); do
  curl -sf -m 2 http://127.0.0.1:5173 >/dev/null 2>&1 && { echo " ready"; break; }
  printf "."; sleep 1
done
echo
echo "  open  http://localhost:5173"
echo "  logs  $LOGS/backend-local.log   $LOGS/frontend-local.log"
