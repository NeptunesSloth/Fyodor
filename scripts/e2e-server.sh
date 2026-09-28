#!/usr/bin/env bash
# Production-mode server for the browser end-to-end tests.
# A fresh data directory with a fixture card database (no Scryfall, no Archidekt, no network),
# serving the built frontend on all interfaces so a second browser can join over the LAN address.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${E2E_PORT:-8765}"
DATA="${E2E_DATA_DIR:-$ROOT/frontend/test-results/e2e-data}"
PY="${PYTHON:-$ROOT/backend/.venv/bin/python}"

rm -rf "$DATA"
mkdir -p "$DATA"
cd "$ROOT/backend"
export FYODOR_DATA_DIR="$DATA" FYODOR_FRONTEND_DIST="$ROOT/frontend/dist" FYODOR_ALLOW_NETWORK=0 FYODOR_LOG_LEVEL=INFO
export FYODOR_HOST=0.0.0.0 FYODOR_PORT="$PORT"
"$PY" -m tools.fixture_db "$DATA/cards.sqlite"
exec "$PY" -m uvicorn --factory app.main:create_app --host 0.0.0.0 --port "$PORT" 2>&1 | tee "$DATA/server.log"
