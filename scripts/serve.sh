#!/usr/bin/env bash
# Production-style single server: builds the frontend and serves it from FastAPI.
# Use FYODOR_HOST=0.0.0.0 to make the table reachable from other devices on your LAN.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${FYODOR_HOST:-127.0.0.1}"
PORT="${FYODOR_PORT:-8000}"

if [ "${SKIP_BUILD:-0}" != "1" ]; then
  (cd "$ROOT/frontend" && npm run build)
fi
cd "$ROOT/backend"
echo "Serving on http://$HOST:$PORT"
exec .venv/bin/uvicorn --factory app.main:create_app --host "$HOST" --port "$PORT"
