#!/usr/bin/env bash
# One-time setup: Python venv for the backend, npm packages for the frontend.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

echo "==> Backend virtualenv"
cd "$ROOT/backend"
[ -d .venv ] || "$PYTHON" -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -e '.[dev]'

echo "==> Frontend packages"
cd "$ROOT/frontend"
npm install

echo
echo "Setup complete. Next:"
echo "  scripts/update-cards.sh        # download the card database (needs Internet once)"
echo "  scripts/dev.sh                 # run backend + frontend in dev mode"
