#!/usr/bin/env bash
# Builds the Windows app (dist/Fyodor/Fyodor.exe, zipped as Fyodor-windows.zip) on Linux, without GitHub Actions:
# the official Windows CPython runs PyInstaller under Wine, with the same flags as scripts/build-app.sh.
#   needs: Ubuntu/Debian with apt (for Wine), curl, python3, Node.js (npm) and Internet the first time
#   WINEPREFIX   where Wine keeps the Windows side (default ~/.cache/fyodor-wine; reused, so later builds are quick)
#   SMOKE=1      also start the built app under Wine and check that it serves (downloads the card database once)
# A Windows PC builds natively with scripts/build-app.sh in Git Bash instead.
set -euo pipefail
# Windows Python under Wine can't start with a closed stdin (a background job, some CI shells): the build reads no input
exec </dev/null
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export WINEPREFIX="${WINEPREFIX:-$HOME/.cache/fyodor-wine}" WINEARCH=win64 WINEDEBUG=-all
# no Mono / Gecko install prompts: the build needs neither
export WINEDLLOVERRIDES="mscoree,mshtml="

# Windows CPython 3.12.10 x64, the official "python" package on nuget.org (a zip with tools/python.exe and pip).
PY_VERSION=3.12.10
PY_URL="https://www.nuget.org/api/v2/package/python/$PY_VERSION"
# SHA-512 as published in nuget.org's catalog for this package (packageHash, base64 there, hex here)
PY_SHA512=bbda4dcf688a94211b62d50968a91b38f305d0b8d1ecd90269f74a86f8a0a4fcebb7ca162a0753a47691eb3df0c964009bd3d8194c6fd19afae8d5fd01e1cc0f

WINE="$(command -v wine64 || command -v wine || true)"
[ -n "$WINE" ] || { [ -x /usr/lib/wine/wine64 ] && WINE=/usr/lib/wine/wine64; }
if [ -z "$WINE" ]; then
  echo "Installing Wine (Ubuntu/Debian package wine64)…"
  sudo_() { if [ "$(id -u)" = 0 ]; then "$@"; else sudo "$@"; fi; }
  sudo_ apt-get update -qq && sudo_ apt-get install -y -qq wine64
  WINE="$(command -v wine64 || command -v wine || echo /usr/lib/wine/wine64)"
fi
"$WINE" --version
# wineserver is a Linux program next to the loader (under Wine, "wine64 wineserver" looks for a Windows program)
WINESERVER="$(command -v wineserver || true)"
[ -n "$WINESERVER" ] || WINESERVER="$(dirname "$WINE")/wineserver"
winpath() { "$WINE" winepath -w "$1" 2>/dev/null | tr -d '\r'; }
# Windows programs under Wine fail to start ("can't initialize sys standard streams") when their output goes straight
# to a file (a build log): every Wine run writes through a pipe instead.
wn() { "$WINE" "$@" 2>&1 | cat; return "${PIPESTATUS[0]}"; }

C="$WINEPREFIX/drive_c"
[ -d "$C" ] || "$WINE" wineboot --init >/dev/null 2>&1 || true
PYDIR="$C/py312-pkg"
if [ ! -x "$PYDIR/tools/python.exe" ] && [ ! -f "$PYDIR/tools/python.exe" ]; then
  echo "Fetching Windows Python $PY_VERSION…"
  tmp="$(mktemp -d)"
  curl -fsSL --retry 3 -o "$tmp/python.nupkg" "$PY_URL"
  echo "$PY_SHA512  $tmp/python.nupkg" | sha512sum -c - >/dev/null || { echo "Python package checksum mismatch: not using it" >&2; exit 1; }
  rm -rf "$PYDIR" && mkdir -p "$PYDIR"
  python3 -I -m zipfile -e "$tmp/python.nupkg" "$PYDIR"
  rm -rf "$tmp"
fi

VENV="$C/fyvenv"
VPY="C:\\fyvenv\\Scripts\\python.exe"
if [ ! -f "$VENV/Scripts/python.exe" ]; then
  echo "Creating the build venv…"
  wn "C:\\py312-pkg\\tools\\python.exe" -m venv "C:\\fyvenv"
fi
# Wine 9 has no CopyFile2, which Python 3.12's shutil.copyfile calls on Windows: hide it so Python uses its fallback.
# (Build venv only: nothing of this reaches the built app.)
echo "import _winapi; hasattr(_winapi, 'CopyFile2') and delattr(_winapi, 'CopyFile2')" > "$VENV/Lib/site-packages/zz_wine_copyfile2.pth"

# A TLS-intercepting proxy's CA (e.g. a CI or sandbox proxy): let Windows pip trust it too
CA="${PIP_CERT:-${REQUESTS_CA_BUNDLE:-${SSL_CERT_FILE:-}}}"
PIP_OPTS=(-q)
[ -n "$CA" ] && [ -f "$CA" ] && PIP_OPTS+=(--cert "$(winpath "$CA")")
wn "$VPY" -m pip install "${PIP_OPTS[@]}" --upgrade pip
wn "$VPY" -m pip install "${PIP_OPTS[@]}" -e "$(winpath "$ROOT/backend")" "pyinstaller>=6"

echo "Building the table (frontend)…"
[ -d "$ROOT/frontend/node_modules" ] || (cd "$ROOT/frontend" && npm ci)
(cd "$ROOT/frontend" && npm run build)

echo "Packaging Fyodor.exe…"
WROOT="$(winpath "$ROOT")"
rm -rf "$ROOT/dist/Fyodor"
# the same flags as scripts/build-app.sh (Windows paths, ";" in --add-data)
(cd "$ROOT/backend" && wn "$VPY" -m PyInstaller --noconfirm --clean --name Fyodor --console \
  --distpath "$WROOT\\dist" --workpath "$WROOT\\build\\pyinstaller" --specpath "$WROOT\\build" \
  --collect-submodules app --collect-submodules tools --collect-submodules uvicorn \
  --add-data "$WROOT\\frontend\\dist;frontend/dist" --icon "$WROOT\\packaging\\windows\\fyodor.ico" \
  "$WROOT\\backend\\app\\launcher.py")
[ -f "$ROOT/dist/Fyodor/Fyodor.exe" ] || { echo "PyInstaller did not produce dist/Fyodor/Fyodor.exe" >&2; exit 1; }

(cd "$ROOT/dist" && rm -f "$ROOT/Fyodor-windows.zip" && python3 -I -m zipfile -c "$ROOT/Fyodor-windows.zip" Fyodor)
echo "Built $ROOT/Fyodor-windows.zip ($(du -h "$ROOT/Fyodor-windows.zip" | cut -f1)); $(file -b "$ROOT/dist/Fyodor/Fyodor.exe" 2>/dev/null || true)"

if [ "${SMOKE:-0}" = "1" ]; then
  echo "Smoke test under Wine…"
  wn "$ROOT/dist/Fyodor/Fyodor.exe" --check || { echo "the app's checks failed" >&2; exit 1; }
  port="${SMOKE_PORT:-18765}"
  mkdir -p "$ROOT/build"
  ("$WINE" "$ROOT/dist/Fyodor/Fyodor.exe" --local --no-browser --port "$port" 2>&1 | cat > "$ROOT/build/smoke.log") &
  ok=0
  for _ in $(seq 1 120); do
    if curl -fsS --noproxy '*' "http://127.0.0.1:$port/api/health" > "$ROOT/build/smoke-health.json" 2>/dev/null; then ok=1; break; fi
    sleep 2
  done
  page="$(curl -fsS --noproxy '*' -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/" 2>/dev/null || true)"
  "$WINESERVER" -k 2>/dev/null || true
  [ "$ok" = 1 ] && [ "$page" = 200 ] || { echo "the app did not serve (see build/smoke.log)" >&2; exit 1; }
  echo "Smoke test passed: $(cat "$ROOT/build/smoke-health.json")"
fi
