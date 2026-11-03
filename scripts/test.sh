#!/usr/bin/env bash
# Run the automated checks on this computer: the same ones CI runs (no GitHub Actions minutes needed).
#   scripts/test.sh            lint, types, the quick backend tests (non-card tests + a fixed sample of the card tests),
#                              frontend typecheck, unit tests and production build
#   E2E=1 scripts/test.sh      also the browser tests (Playwright) against the production build
#   FULL=1 scripts/test.sh     the whole backend suite instead of the quick sample (40,000+ tests: hours; needs the full
#                              card database in data/cards.sqlite)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"

echo "==> Backend: ruff"
(cd "$ROOT/backend" && "$PY" -m ruff check .)
echo "==> Backend: mypy"
(cd "$ROOT/backend" && "$PY" -m mypy app tools)
PARALLEL=()
"$PY" -c "import xdist" 2>/dev/null && PARALLEL=(-n auto)
if [ "${FULL:-0}" = "1" ]; then
  echo "==> Backend: pytest (full suite)"
  (cd "$ROOT/backend" && "$PY" -m pytest -q "${PARALLEL[@]}")
else
  echo "==> Backend: pytest (quick: as CI's every-push job)"
  # shellcheck disable=SC2046  # the shard tool prints one test path per word
  (cd "$ROOT/backend" && "$PY" -m pytest -q "${PARALLEL[@]}" $("$PY" -m tools.test_shards --quick))
fi
echo "==> Frontend: typecheck"
(cd "$ROOT/frontend" && npm run --silent typecheck)
echo "==> Frontend: vitest"
(cd "$ROOT/frontend" && npm run --silent test)
echo "==> Frontend: production build"
(cd "$ROOT/frontend" && npm run --silent build)
if [ "${E2E:-0}" = "1" ]; then
  echo "==> Frontend: Playwright"
  (cd "$ROOT/frontend" && CI=1 npx playwright test)
fi
echo "All checks passed."
