#!/usr/bin/env bash
# Builds the Windows installer, Fyodor-Setup-<version>.exe, from the Windows app in dist/Fyodor (NSIS, packaging/windows/fyodor.nsi).
#   Linux: builds dist/Fyodor first with scripts/build-windows-wine.sh when it's missing (or REBUILD=1), then runs makensis
#          (Ubuntu/Debian package nsis, installed if missing).
#   Windows (Git Bash): build dist/Fyodor with scripts/build-app.sh first, and have NSIS 3 (makensis) on PATH.
#   BROWSER_DIR=<unpacked Chromium for Windows (chrome-win)>  ships it as Fyodor's own window (dist/Fyodor/browser), so the
#            table never depends on the computer's own browser (an offline computer's Edge can't be updated)
#   LEGACY_BROWSER_DIR=<unpacked Chromium 109 for Windows>  the window on Windows 8.1, where current Chromium won't run
#            (dist/Fyodor/browser-legacy; 109 was the last Chromium for Windows 7 and 8)
#   CARDS_DB=<a cards.sqlite>  ships it as the card database Fyodor starts with (dist/Fyodor/seed), so not even the first
#            start needs the Internet. With both, the one installer file is everything an offline computer needs.
#   TOKEN_IMAGES=<an image cache's tokens/ folder (python -m tools.update_cards --images tokens)>  ships every token's art
#            (dist/Fyodor/seed/images/tokens), read in place by the server when its own cache has none: token art offline
#   SMOKE=1  (Linux) installs the result silently into a fresh Wine prefix, starts the installed app, checks that it serves,
#            then uninstalls it silently and checks that its files are gone.
set -euo pipefail
exec </dev/null
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/backend/pyproject.toml" | head -1)"
OUT="$ROOT/Fyodor-Setup-$VERSION.exe"
WINDOWS=0
case "$(uname -s)" in MINGW* | MSYS* | CYGWIN*) WINDOWS=1 ;; esac

if [ ! -f "$ROOT/dist/Fyodor/Fyodor.exe" ] || [ "${REBUILD:-0}" = "1" ]; then
  if [ "$WINDOWS" = 1 ]; then
    echo "Build the app first: scripts/build-app.sh" >&2
    exit 1
  fi
  "$ROOT/scripts/build-windows-wine.sh"
fi

if ! command -v makensis >/dev/null; then
  [ "$WINDOWS" = 0 ] || { echo "Install NSIS 3 (https://nsis.sourceforge.io) and put makensis on PATH." >&2; exit 1; }
  echo "Installing NSIS (Ubuntu/Debian package nsis)…"
  sudo_() { if [ "$(id -u)" = 0 ]; then "$@"; else sudo "$@"; fi; }
  sudo_ apt-get update -qq && sudo_ apt-get install -y -qq nsis
fi

SRC="$ROOT/dist/Fyodor"
# A Chromium snapshot carries programs a player never runs (its UI test suite alone is 375 MB, plus installers) and 200+ language packs:
# only the window and English stay
prune_browser() {
  find "$1" -maxdepth 1 -type f \( -name '*_tests.exe' -o -name 'setup.exe' -o -name 'mini_installer.exe' -o -name 'chromedriver.exe' \) -delete
  find "$1/locales" -type f ! -name 'en-US.pak' ! -name 'en-US.pak.info' -delete 2>/dev/null || true
}
rm -rf "$SRC/browser" "$SRC/browser-legacy" "$SRC/seed"
if [ -n "${BROWSER_DIR:-}" ]; then
  [ -f "$BROWSER_DIR/chrome.exe" ] || { echo "BROWSER_DIR has no chrome.exe: $BROWSER_DIR" >&2; exit 1; }
  cp -r "$BROWSER_DIR" "$SRC/browser"
  prune_browser "$SRC/browser"
fi
if [ -n "${LEGACY_BROWSER_DIR:-}" ]; then
  [ -f "$LEGACY_BROWSER_DIR/chrome.exe" ] || { echo "LEGACY_BROWSER_DIR has no chrome.exe: $LEGACY_BROWSER_DIR" >&2; exit 1; }
  cp -r "$LEGACY_BROWSER_DIR" "$SRC/browser-legacy"
  prune_browser "$SRC/browser-legacy"
fi
if [ -n "${TOKEN_IMAGES:-}" ]; then
  [ -d "$TOKEN_IMAGES" ] || { echo "no token images at $TOKEN_IMAGES" >&2; exit 1; }
  mkdir -p "$SRC/seed/images/tokens" && cp -r "$TOKEN_IMAGES/." "$SRC/seed/images/tokens/"
fi
if [ -n "${CARDS_DB:-}" ]; then
  [ -f "$CARDS_DB" ] || { echo "no card database at $CARDS_DB" >&2; exit 1; }
  mkdir -p "$SRC/seed" && cp "$CARDS_DB" "$SRC/seed/cards.sqlite"
fi
[ "$WINDOWS" = 1 ] && SRC="$(cygpath -w "$SRC")" && OUT="$(cygpath -w "$OUT")"
rm -f "$OUT"
(cd "$ROOT/packaging/windows" && makensis -V2 -DVERSION="$VERSION" -DSRC="$SRC" -DOUT="$OUT" fyodor.nsi)
echo "Built $OUT ($(du -h "$OUT" | cut -f1))"

if [ "${SMOKE:-0}" = "1" ] && [ "$WINDOWS" = 0 ]; then
  echo "Smoke test under Wine: install, start, uninstall…"
  WINE="$(command -v wine64 || command -v wine || echo /usr/lib/wine/wine64)"
  WINESERVER="$(command -v wineserver || echo "$(dirname "$WINE")/wineserver")"
  # a fresh Windows each time (under build/, which git ignores)
  export WINEPREFIX="${SMOKE_PREFIX:-$ROOT/build/installer-wine}" WINEARCH=win64 WINEDEBUG=-all WINEDLLOVERRIDES="mscoree,mshtml="
  rm -rf "$WINEPREFIX"
  wn() { "$WINE" "$@" 2>&1 | cat; return "${PIPESTATUS[0]}"; }
  "$WINE" wineboot --init >/dev/null 2>&1 || true
  # /D= must be last and unquoted (NSIS)
  setup="$("$WINE" winepath -w "$OUT" 2>/dev/null | tr -d '\r')"
  wn "$setup" /S '/D=C:\Fyodor' || true
  APP="$WINEPREFIX/drive_c/Fyodor"
  for f in Fyodor.exe fyodor.ico "Uninstall Fyodor.exe" _internal; do
    [ -e "$APP/$f" ] || { echo "the installer did not put $f in C:\\Fyodor" >&2; exit 1; }
  done
  [ -f "$WINEPREFIX/drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/Fyodor.lnk" ] \
    || { echo "no Start-menu shortcut for all users" >&2; exit 1; }
  if [ -n "${BROWSER_DIR:-}" ]; then [ -f "$APP/browser/chrome.exe" ] || { echo "the installer did not put Fyodor's window in" >&2; exit 1; }; fi
  if [ -n "${LEGACY_BROWSER_DIR:-}" ]; then [ -f "$APP/browser-legacy/chrome.exe" ] || { echo "the installer did not put the Windows 8.1 window in" >&2; exit 1; }; fi
  if [ -n "${TOKEN_IMAGES:-}" ]; then [ -d "$APP/seed/images/tokens" ] && [ ! -e "$APP/seed/images/tokens/tokens" ] || { echo "the installer did not put the token art in (or nested it)" >&2; exit 1; }; fi
  if [ -n "${CARDS_DB:-}" ]; then [ -f "$APP/seed/cards.sqlite" ] || { echo "the installer did not put the card database in" >&2; exit 1; }; fi
  wn 'C:\Fyodor\Fyodor.exe' --check || { echo "the installed app's checks failed" >&2; exit 1; }
  port="${SMOKE_PORT:-18766}"
  mkdir -p "$ROOT/build"
  ("$WINE" 'C:\Fyodor\Fyodor.exe' --local --no-browser --port "$port" 2>&1 | cat > "$ROOT/build/installer-smoke.log") &
  ok=0
  for _ in $(seq 1 150); do
    if curl -fsS --noproxy '*' "http://127.0.0.1:$port/api/health" > "$ROOT/build/installer-health.json" 2>/dev/null; then ok=1; break; fi
    sleep 2
  done
  page="$(curl -fsS --noproxy '*' -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/" 2>/dev/null || true)"
  "$WINESERVER" -k 2>/dev/null || true
  [ "$ok" = 1 ] && [ "$page" = 200 ] || { echo "the installed app did not serve (see build/installer-smoke.log)" >&2; exit 1; }
  if [ -n "${CARDS_DB:-}" ]; then  # a fresh Windows: the first start put the shipped card database in place, no download
    grep -q '"available":true' "$ROOT/build/installer-health.json" || { echo "the first start did not put the card database in place" >&2; exit 1; }
  fi
  # _?= runs the uninstaller in place and waits for it (it can't delete itself then, so that one file stays)
  wn 'C:\Fyodor\Uninstall Fyodor.exe' /S '_?=C:\Fyodor' || true
  "$WINESERVER" -w 2>/dev/null || true
  for f in Fyodor.exe fyodor.ico _internal browser browser-legacy seed; do
    [ ! -e "$APP/$f" ] || { echo "the uninstaller left $f behind" >&2; exit 1; }
  done
  [ ! -e "$WINEPREFIX/drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/Fyodor.lnk" ] \
    || { echo "the uninstaller left the Start-menu shortcut" >&2; exit 1; }
  # the user's data (decks, saves, card database) is in their profile and must survive an uninstall
  [ -d "$WINEPREFIX/drive_c/users/$(id -un)/Fyodor" ] || echo "note: no user data folder was created by the smoke run"
  echo "Installer smoke test passed: installed, served $(cat "$ROOT/build/installer-health.json" | head -c 80)…, uninstalled."
fi
