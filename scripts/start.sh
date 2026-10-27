#!/usr/bin/env bash
# Game-night start: sets things up the first time, builds the table interface if needed, then
# starts Fyodor, prints the address for the rest of the pod and opens your browser.
#   scripts/start.sh            # the pod on your network can join (open the address it prints)
#   scripts/start.sh --local    # this computer only
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v python3 >/dev/null || { echo "Fyodor needs Python 3.11 or newer: https://www.python.org/downloads/"; exit 1; }
if [ ! -f "$ROOT/frontend/dist/index.html" ] && ! command -v npm >/dev/null; then
  echo "Fyodor needs Node.js the first time (to build the table): https://nodejs.org (LTS)"; exit 1
fi
if [ ! -x "$ROOT/backend/.venv/bin/python" ] || [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "First run: installing Fyodor (one time)…"
  "$ROOT/scripts/setup.sh"
fi
if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  (cd "$ROOT/frontend" && npm run build)
fi
cd "$ROOT/backend"
exec .venv/bin/python -m app.launcher "$@"
