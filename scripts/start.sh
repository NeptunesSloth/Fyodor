#!/usr/bin/env bash
# Game-night start: sets things up the first time, builds the table interface if needed, then
# starts Fyodor, prints the address for the rest of the pod and opens your browser.
#   scripts/start.sh            # this computer only
#   scripts/start.sh --lan      # let other devices on your home network join
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ ! -x "$ROOT/backend/.venv/bin/python" ] || [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "First run: installing Fyodor (one time)…"
  "$ROOT/scripts/setup.sh"
fi
if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  (cd "$ROOT/frontend" && npm run build)
fi
cd "$ROOT/backend"
exec .venv/bin/python -m app.launcher "$@"
