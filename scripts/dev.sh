#!/usr/bin/env bash
# Run backend (uvicorn, :8000) and frontend (vite, :5173) together. Ctrl+C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${FYODOR_HOST:-127.0.0.1}"
PORT="${FYODOR_PORT:-8000}"

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd "$ROOT/backend" && FYODOR_DEV_TOOLS=1 FYODOR_TRUSTED_PROXIES=127.0.0.1 .venv/bin/uvicorn --factory app.main:create_app --reload --host "$HOST" --port "$PORT") &
(cd "$ROOT/frontend" && FYODOR_BACKEND_URL="http://127.0.0.1:$PORT" npm run dev -- --host "$HOST") &
wait
