#!/usr/bin/env bash
# Builds the downloadable Fyodor app for this computer's OS: no Python or Node needed to run it.
# Output: dist/Fyodor/ (zip it to share). Run once per OS (Windows via Git Bash, macOS, Linux).
#   needs: Node.js and Python 3.11+ (the backend venv is made if missing)
#   BROWSER_DIR=<unpacked Chromium for Windows (chrome-win64)>  ships it as Fyodor's own window (dist/Fyodor/browser), as the
#            installer does; LEGACY_BROWSER_DIR=<Chromium 109> for Windows 8.1 (dist/Fyodor/browser-legacy). Or run
#            scripts/add-portable-browser.sh after a build.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -d "$ROOT/backend/.venv" ] || python3 -m venv "$ROOT/backend/.venv" 2>/dev/null || python -m venv "$ROOT/backend/.venv"
PY="$ROOT/backend/.venv/bin/python"; [ -x "$PY" ] || PY="$ROOT/backend/.venv/Scripts/python.exe"
[ -d "$ROOT/frontend/node_modules" ] || (cd "$ROOT/frontend" && npm ci)
(cd "$ROOT/frontend" && npm run build)
"$PY" -m pip install -q -e "$ROOT/backend" "pyinstaller>=6"
# PyInstaller is a native program: on Windows (Git Bash) give it a Windows path and Windows's ";" between the two halves of
# --add-data. A POSIX path like /d/a/... with ":" gets mangled by Git Bash's path conversion (seen in CI: \d\a\...\frontend\dist).
DATA_ROOT="$ROOT"; DATA_SEP=":"; ICON=()
case "$(uname -s)" in MINGW* | MSYS* | CYGWIN*) DATA_ROOT="$(cygpath -m "$ROOT")"; DATA_SEP=";"; ICON=(--icon "$DATA_ROOT/packaging/windows/fyodor.ico") ;; esac
cd "$ROOT/backend"
# app.rules loads some card modules by name, so every module is collected explicitly
"$PY" -m PyInstaller --noconfirm --clean --name Fyodor --console \
  --distpath "$ROOT/dist" --workpath "$ROOT/build/pyinstaller" --specpath "$ROOT/build" \
  --collect-submodules app --collect-submodules tools --collect-submodules uvicorn \
  --add-data "$DATA_ROOT/frontend/dist${DATA_SEP}frontend/dist" --add-data "$DATA_ROOT/backend/app/decks/precons.json${DATA_SEP}app/decks" ${ICON[@]+"${ICON[@]}"} \
  app/launcher.py
if [ -n "${BROWSER_DIR:-}" ]; then "$ROOT/scripts/add-portable-browser.sh" "$BROWSER_DIR" ${LEGACY_BROWSER_DIR:+"$LEGACY_BROWSER_DIR"}; fi
echo "Built $ROOT/dist/Fyodor — double-click Fyodor (Fyodor.exe on Windows) inside it."
