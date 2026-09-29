#!/usr/bin/env bash
# Run all automated checks: backend lint + tests, frontend typecheck + tests.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Backend: ruff"
(cd "$ROOT/backend" && .venv/bin/ruff check .)
echo "==> Backend: mypy"
(cd "$ROOT/backend" && .venv/bin/mypy app tools)
echo "==> Backend: pytest"
(cd "$ROOT/backend" && .venv/bin/pytest)
echo "==> Frontend: typecheck"
(cd "$ROOT/frontend" && npm run --silent typecheck)
echo "==> Frontend: vitest"
(cd "$ROOT/frontend" && npm run --silent test)
if [ "${E2E:-0}" = "1" ]; then
  echo "==> Frontend: production build + Playwright"
  (cd "$ROOT/frontend" && npm run --silent build && npx playwright test)
fi
