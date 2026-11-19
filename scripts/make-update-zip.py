#!/usr/bin/env python3
"""Build a changes-only Fyodor update zip: the files of a new build (dist/Fyodor) that differ from what the computers already have.

    python scripts/make-update-zip.py --prev dist/Fyodor-portable-2026-11-17d.zip --prev dist/Fyodor-update-2026-11-17e.zip \
        --version 2026-11-18a --out dist/Fyodor-update-2026-11-18a.zip

``--prev``: what the computers have now: the portable zip they were set up with, then each update installed since, oldest first (a later one
wins). A file is compared by size and CRC-32 against the newest copy among them (read from the zips' own directory: nothing is unpacked).
Files that are new or changed go in as ``Fyodor/<path>``, with ``Fyodor/update-manifest.json``: the version, the commit, every file with its
size and SHA-256 (Settings → Install update checks them), and the files the new build no longer has (listed; the updater leaves them).
``seed/`` (the card database and art the installer carries) is never listed as removed when the new build has none: pass ``--keep`` to
change which folders that applies to. Without ``--prev`` every file of the build goes in (a full update).

Standard library only; runs anywhere Python 3.10+ does. Install the result from Settings → Update Fyodor → Install update…, or unzip it over
the Fyodor folder while Fyodor is closed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = "Fyodor"
MANIFEST = "update-manifest.json"
SKIP_TOP = {"_update", "_update_backup"}  # the updater's own working folders, never shipped
CHUNK = 1024 * 1024


def rel_of(name: str) -> str | None:
    """'Fyodor\\_internal\\x.dll' or 'Fyodor/_internal/x.dll' → '_internal/x.dll'; None for folders and anything outside Fyodor/."""
    parts = name.replace("\\", "/").split("/")
    if len(parts) < 2 or parts[0] != ROOT or not parts[-1]:
        return None
    return "/".join(parts[1:])


def baseline(zips: list[Path]) -> dict[str, tuple[int, int, str]]:
    """lower-cased path → (size, crc32, path) of the newest copy of each file among the zips (later zips win; Windows paths ignore case)."""
    have: dict[str, tuple[int, int, str]] = {}
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for zi in zf.infolist():
                rel = rel_of(zi.filename)
                if rel is not None and rel != MANIFEST:
                    have[rel.lower()] = (zi.file_size, zi.CRC, rel)
    return have


def crc_and_sha(path: Path) -> tuple[int, str]:
    crc = 0
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            crc = zlib.crc32(chunk, crc)
            sha.update(chunk)
    return crc & 0xFFFFFFFF, sha.hexdigest()


def build_files(new: Path) -> list[tuple[str, Path]]:
    out = []
    for p in sorted(new.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(new).as_posix()
        if rel.split("/", 1)[0] in SKIP_TOP or rel == MANIFEST:
            continue
        out.append((rel, p))
    return out


def git_commit(repo: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True, check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description="Build a changes-only Fyodor update zip.")
    ap.add_argument("--new", type=Path, default=repo / "dist" / "Fyodor", help="the new build's folder (default: dist/Fyodor)")
    ap.add_argument("--prev", type=Path, action="append", default=[], help="a zip the computers already have (repeat, oldest first)")
    ap.add_argument("--out", type=Path, help="the update zip to write (default: dist/Fyodor-update-<version>.zip)")
    ap.add_argument("--version", default=dt.date.today().isoformat(), help="the version shown in Settings (default: today's date)")
    ap.add_argument("--commit", default=None, help="the commit it was built from (default: this checkout's HEAD)")
    ap.add_argument("--keep", action="append", default=None, help="a top folder never listed as removed (default: seed)")
    ap.add_argument("--dry-run", action="store_true", help="only list what would go in")
    args = ap.parse_args(argv)

    new: Path = args.new
    if not (new / "Fyodor.exe").is_file() and not (new / "Fyodor").is_file():
        print(f"{new} doesn't look like a Fyodor build (no Fyodor.exe)", file=sys.stderr)
        return 2
    keep = {k.strip("/\\").lower() for k in (args.keep if args.keep is not None else ["seed"])}
    have = baseline(args.prev)
    files = build_files(new)
    changed: list[tuple[str, Path, int, str]] = []
    for rel, p in files:
        size = p.stat().st_size
        crc, sha = crc_and_sha(p)
        if have.get(rel.lower(), (None, None, ""))[:2] != (size, crc):
            changed.append((rel, p, size, sha))
    present = {rel.lower() for rel, _ in files}
    removed = sorted(v[2] for k, v in have.items() if k not in present and k.split("/", 1)[0] not in keep) if args.prev else []
    total = sum(c[2] for c in changed)
    print(f"{len(files):,} files in {new}; {len(changed):,} new or changed ({total / 1024 / 1024:.1f} MB)"
          + (f" against {len(args.prev)} earlier zip(s)" if args.prev else " (no --prev: a full update)"))
    for rel, _, size, _ in changed[:40]:
        print(f"  + {rel}  ({size:,} bytes)")
    if len(changed) > 40:
        print(f"  … and {len(changed) - 40:,} more")
    if removed:
        print(f"{len(removed):,} file(s) the new build no longer has (listed in the manifest; the updater leaves them):")
        for r in removed[:40]:
            print(f"  - {r}")
        if len(removed) > 40:
            print(f"  … and {len(removed) - 40:,} more")
    if not changed:
        print("Nothing changed: no update written.")
        return 1
    if args.dry_run:
        return 0
    manifest = {"format": 1, "app": "Fyodor", "version": args.version, "commit": args.commit or git_commit(repo),
                "built_at": dt.datetime.now().replace(microsecond=0).isoformat(), "base": [p.name for p in args.prev],
                "files": [{"path": rel, "size": size, "sha256": sha} for rel, _, size, sha in changed], "removed": removed}
    out: Path = args.out or (repo / "dist" / f"Fyodor-update-{args.version}.zip")
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")
    with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(f"{ROOT}/{MANIFEST}", json.dumps(manifest, indent=1))
        for rel, p, _, _ in changed:
            zf.write(p, f"{ROOT}/{rel}")
    part.replace(out)
    print(f"Wrote {out} ({out.stat().st_size / 1024 / 1024:.1f} MB), version {manifest['version']}, commit {manifest['commit'] or '?'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
