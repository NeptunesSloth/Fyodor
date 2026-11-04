#!/usr/bin/env bash
# Renders packaging/windows/fyodor-icon*.svg into fyodor.ico (16–256 px) for Fyodor.exe, the installer and its shortcuts.
# Needs Node with Playwright's Chromium (the frontend's dev dependency; PW_CHROMIUM=<chrome path> picks another build) and
# Python 3 with Pillow.
# The .ico is committed, so a build doesn't need to run this; rerun it after changing the SVG.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
# 16–32 px use the simplified fyodor-icon-small.svg (one card, a bold F); 48 px and up the full artwork.
(cd "$ROOT/frontend" && SVG="$HERE/fyodor-icon.svg" SMALL="$HERE/fyodor-icon-small.svg" OUT="$tmp" node -e '
const { chromium } = require("playwright");
const fs = require("fs");
(async () => {
  const full = fs.readFileSync(process.env.SVG, "utf8");
  const small = fs.readFileSync(process.env.SMALL, "utf8");
  const browser = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});
  for (const size of [16, 24, 32, 48, 64, 128, 256]) {
    const svg = size <= 32 ? small : full;
    const page = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
    await page.setContent(`<html><body style="margin:0;background:transparent">${svg.replace("<svg ", `<svg style="display:block;width:${size}px;height:${size}px" `)}</body></html>`);
    await page.screenshot({ path: `${process.env.OUT}/${size}.png`, omitBackground: true });
    await page.close();
  }
  await browser.close();
})();')
python3 -I - "$tmp" "$HERE/fyodor.ico" <<'EOF'
import sys
from pathlib import Path
from PIL import Image
src, out = Path(sys.argv[1]), sys.argv[2]
sizes = [16, 24, 32, 48, 64, 128, 256]
images = [Image.open(src / f"{s}.png").convert("RGBA") for s in sizes]
# each size rendered from the SVG at that size (crisper than downscaling one bitmap)
images[-1].save(out, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[:-1])
print("wrote", out)
EOF
