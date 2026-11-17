#!/usr/bin/env bash
# Puts Fyodor's own window into the portable app (dist/Fyodor/browser, where the launcher looks for chrome.exe), so the
# table never depends on the computer's own browser (an offline computer's Edge can't be updated). Run after build-app.sh
# (PyInstaller replaces dist/Fyodor), then zip dist/Fyodor. The browser is never committed: dist/ is ignored by git.
#   usage: scripts/add-portable-browser.sh <unpacked Chromium for Windows (chrome-win64)> [<Chromium 109 for Windows 8.1>]
#   (Chromium: Chrome for Testing's Stable "chrome" win64 zip, https://googlechromelabs.github.io/chrome-for-testing/)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/dist/Fyodor"
[ -d "$APP" ] || { echo "Build the app first: scripts/build-app.sh" >&2; exit 1; }
add() {  # <chromium dir> <folder name in dist/Fyodor>
  [ -f "$1/chrome.exe" ] || { echo "no chrome.exe in $1" >&2; exit 1; }
  rm -rf "${APP:?}/$2"
  cp -r "$1" "$APP/$2"
  "$ROOT/scripts/prune-browser.sh" "$APP/$2"
  echo "Added $APP/$2 ($(du -sh "$APP/$2" | cut -f1))"
}
add "${1:?usage: add-portable-browser.sh <chromium dir> [<legacy chromium dir>]}" browser
if [ -n "${2:-}" ]; then add "$2" browser-legacy; fi
