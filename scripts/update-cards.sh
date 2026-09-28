#!/usr/bin/env bash
# Download/refresh the local card database (and optionally images). Pass --help for options.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
exec .venv/bin/python -m tools.update_cards "$@"
