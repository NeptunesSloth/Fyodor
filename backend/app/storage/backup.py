"""BACKUP FYODOR / restore, pre-migration backups and the database recovery mode.

* ``create_backup`` writes ``data/backups/fyodor-backup-<time>.zip``: a consistent copy of
  ``app.sqlite`` (decks, saves, pod stats, macros, assets index, live tables) and the custom
  asset files (sleeves, playmats). The card database is not included: it is rebuilt from
  Scryfall data and would make every backup hundreds of megabytes.
* ``stage_restore`` validates an uploaded or listed backup (only the expected file names, no
  paths, size limits, a readable SQLite database) and stages it; ``apply_pending_restore``
  swaps it in on the next start, after backing up the current database. Nothing is ever
  executed from a backup.
* ``pre_migration_backup`` copies the database before a schema migration runs.
* ``open_or_recover`` opens the app database; if it is damaged, the file is moved aside, a
  fresh database is created, and the app starts in *recovery mode* so the host can restore a
  backup from Settings.
"""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
import sqlite3
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app import __version__

log = logging.getLogger(__name__)

BACKUP_NAME = re.compile(r"^fyodor-backup-\d{8}-\d{6}(-\d+)?\.zip$")
ASSET_NAME = re.compile(r"^assets/[0-9a-f]{64}\.(png|jpg|jpeg|webp)$")
MAX_BACKUP_BYTES = 2 * 1024 * 1024 * 1024
KEEP_BACKUPS = 12


class BackupError(ValueError):
    pass


@dataclass
class RecoveryInfo:
    """Set when the app started without its normal database."""

    reason: str
    moved_to: str | None = None
    backups: list[str] = field(default_factory=list)


def backups_dir(data_dir: Path) -> Path:
    d = data_dir / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def copy_sqlite(src: sqlite3.Connection | Path, dest: Path) -> None:
    """A consistent copy of a live SQLite database (the backup API, safe under WAL)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    source = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True) if isinstance(src, Path) else src
    try:
        target = sqlite3.connect(tmp)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        if isinstance(src, Path):
            source.close()
    tmp.replace(dest)


def schema_version(path: Path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    except sqlite3.DatabaseError:
        return 0
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.DatabaseError:  # missing table, or a damaged file (recovery mode handles that)
        return 0
    finally:
        conn.close()


def pre_migration_backup(path: Path, target_version: int) -> Path | None:
    """Copy the database aside before migrating it to ``target_version`` (if it needs it)."""
    current = schema_version(path)
    if current == 0 or current >= target_version:
        return None
    dest = backups_dir(path.parent) / f"app-before-v{target_version}-{time.strftime('%Y%m%d-%H%M%S')}.sqlite"
    copy_sqlite(path, dest)
    log.info("Backed up the database before migrating v%d → v%d: %s", current, target_version, dest.name)
    return dest


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(1, 1000):
        cand = path.with_name(f"{path.stem}-{i}{path.suffix}")
        if not cand.exists():
            return cand
    raise BackupError("Too many backups with the same name")


def create_backup(data_dir: Path, conn: sqlite3.Connection, lock: Any, assets_dir: Path) -> dict[str, Any]:
    out_dir = backups_dir(data_dir)
    dest = _unique(out_dir / f"fyodor-backup-{time.strftime('%Y%m%d-%H%M%S')}.zip")
    tmp_db = out_dir / ".backup-app.sqlite"
    with lock:
        copy_sqlite(conn, tmp_db)
    files = 0
    try:
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_db, "app.sqlite")
            if assets_dir.is_dir():
                for f in sorted(assets_dir.iterdir()):
                    if f.is_file() and ASSET_NAME.match(f"assets/{f.name}"):
                        zf.write(f, f"assets/{f.name}")
                        files += 1
            manifest = {"format": "fyodor-backup", "version": 1, "app_version": __version__,
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "schema_version": schema_version(tmp_db),
                        "assets": files}
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    finally:
        tmp_db.unlink(missing_ok=True)
    for old in list_backups(data_dir)[KEEP_BACKUPS:]:
        (out_dir / old["name"]).unlink(missing_ok=True)
    return describe(dest)


def describe(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {"name": path.name, "size": st.st_size, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime))}


def list_backups(data_dir: Path) -> list[dict[str, Any]]:
    d = backups_dir(data_dir)
    files = [f for f in d.iterdir() if f.is_file() and BACKUP_NAME.match(f.name)]
    return [describe(f) for f in sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)]


def backup_path(data_dir: Path, name: str) -> Path:
    """A listed backup by name only (never a client-supplied path)."""
    if not BACKUP_NAME.match(name):
        raise BackupError("Not a Fyodor backup name")
    path = backups_dir(data_dir) / name
    if not path.is_file():
        raise BackupError("No such backup")
    return path


def _pending_dir(data_dir: Path) -> Path:
    return data_dir / "restore-pending"


def stage_restore(data_dir: Path, blob: bytes) -> dict[str, Any]:
    """Validate a backup and stage it; it is applied when Fyodor starts next."""
    if len(blob) > MAX_BACKUP_BYTES:
        raise BackupError("Backup is too large")
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise BackupError("Not a zip file") from exc
    with zf:
        names = zf.namelist()
        if "manifest.json" not in names or "app.sqlite" not in names:
            raise BackupError("Not a Fyodor backup (manifest.json or app.sqlite missing)")
        for info in zf.infolist():
            if info.is_dir():
                continue
            if info.filename not in ("manifest.json", "app.sqlite") and not ASSET_NAME.match(info.filename):
                raise BackupError(f"Unexpected file in backup: {info.filename[:80]}")
        if sum(i.file_size for i in zf.infolist()) > MAX_BACKUP_BYTES:
            raise BackupError("Backup is too large when unpacked")
        try:
            manifest = json.loads(zf.read("manifest.json"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise BackupError("Broken manifest") from exc
        if not isinstance(manifest, dict) or manifest.get("format") != "fyodor-backup":
            raise BackupError("Not a Fyodor backup")
        pending = _pending_dir(data_dir)
        if pending.exists():
            shutil.rmtree(pending)
        (pending / "assets").mkdir(parents=True)
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = pending / info.filename  # names were checked against a strict allowlist above
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    db = pending / "app.sqlite"
    try:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.execute("SELECT version FROM schema_version").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        shutil.rmtree(pending, ignore_errors=True)
        raise BackupError("The database in this backup is damaged") from exc
    if ok != "ok":
        shutil.rmtree(pending, ignore_errors=True)
        raise BackupError("The database in this backup is damaged")
    return {"staged": True, "created_at": manifest.get("created_at"), "app_version": manifest.get("app_version"),
            "restart_required": True}


def apply_pending_restore(data_dir: Path, app_db: Path, assets_dir: Path) -> bool:
    """On start: swap a staged backup in (the current database is backed up first)."""
    pending = _pending_dir(data_dir)
    staged = pending / "app.sqlite"
    if not staged.is_file():
        return False
    if app_db.exists():
        keep = backups_dir(data_dir) / f"app-before-restore-{time.strftime('%Y%m%d-%H%M%S')}.sqlite"
        try:
            copy_sqlite(app_db, keep)
        except sqlite3.DatabaseError:
            shutil.copy2(app_db, keep)  # a damaged database is still worth keeping
    for suffix in ("", "-wal", "-shm"):
        Path(f"{app_db}{suffix}").unlink(missing_ok=True)
    shutil.move(str(staged), app_db)
    assets_dir.mkdir(parents=True, exist_ok=True)
    for f in (pending / "assets").iterdir():
        if f.is_file() and not (assets_dir / f.name).exists():
            shutil.move(str(f), assets_dir / f.name)
    shutil.rmtree(pending, ignore_errors=True)
    log.warning("Restored the database from a backup")
    return True


def quarantine_damaged(app_db: Path) -> Path:
    """Move a damaged database (and its WAL files) aside; returns where it went."""
    d = app_db.parent / "recovery"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"app-damaged-{time.strftime('%Y%m%d-%H%M%S')}.sqlite"
    for suffix in ("", "-wal", "-shm"):
        src = Path(f"{app_db}{suffix}")
        if src.exists():
            shutil.move(str(src), f"{dest}{suffix}")
    return dest
