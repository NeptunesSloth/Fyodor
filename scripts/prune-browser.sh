#!/usr/bin/env bash
# Trims an unpacked Chromium for Windows (chrome-win / chrome-win64) in place to what Fyodor's window needs.
#   usage: scripts/prune-browser.sh <chromium dir>
# A Chromium snapshot carries programs a player never runs (its UI test suite alone is 375 MB, plus installers) and 200+
# language packs: only the window and English stay. Used by build-windows-installer.sh and add-portable-browser.sh.
set -euo pipefail
dir="${1:?usage: prune-browser.sh <chromium dir>}"
[ -f "$dir/chrome.exe" ] || { echo "no chrome.exe in $dir" >&2; exit 1; }
find "$dir" -maxdepth 1 -type f \( -name '*_tests.exe' -o -name 'setup.exe' -o -name 'mini_installer.exe' -o -name 'chromedriver.exe' \) -delete
find "$dir/locales" -type f ! -name 'en-US.pak' ! -name 'en-US.pak.info' -delete 2>/dev/null || true
