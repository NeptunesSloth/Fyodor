"""BACKUP FYODOR / restore, pre-migration backups and the database recovery mode.

* ``create_backup`` writes ``data/backups/fyodor-backup-<time>.zip`` (``fyodor-autobackup-`` for the automatic
  ones, see ``app/storage/autobackup.py``): a consistent copy of
  ``app.sqlite`` (decks, saves, pod stats, macros, assets index, live tables) and the custom
  asset files (sleeves, playmats). The card database is not included: it is rebuilt from
  Scryfall data and would make every backup hundreds of megabytes.
* A backup made by hand also carries the card art the saved decks need to be played offline
  (``deck_art``: the cached images of their printings and of the tokens they make, every cached
  face and size, plus the card back and the mana symbols) under ``images/``, laid out like the
  image cache (``images/cards/<id[:2]>/<id>-<face>-<size>.jpg`` …). Only what the decks need,
  never the whole cache; stored, not deflated (JPEGs don't shrink); art stops being added near
  ``MAX_BACKUP_BYTES`` (the manifest counts what was left out). Automatic backups never carry
  art: a dozen of them are kept.
* ``stage_restore`` validates an uploaded or listed backup (only the expected file names, no
  paths, size limits, a readable SQLite database) and stages it; ``apply_pending_restore``
  swaps it in on the next start, after backing up the current database. Art is checked name by
  name against the image cache's own layout (a UUID with a known face and size, the card back's
  id, a symbol code) and by content (a JPEG, a plain SVG, ``MAX_ART_BYTES`` each; anything else
  is left out), and only fills gaps in the cache: art already there is never replaced. Nothing
  is ever executed from a backup.
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
from app.cards.images import CARD_BACK_ID, IMAGE_SIZES, MAX_FACES, SYMBOL_INDEX, UUID_RE, ImageStore

log = logging.getLogger(__name__)

BACKUP_NAME = re.compile(r"^fyodor-(auto)?backup-\d{8}-\d{6}(-\d+)?\.zip$")
AUTO_PREFIX = "fyodor-autobackup-"
BROWSER_DECKS = "browser-decks.json"  # the host browser's "My decks" (kept in browser storage, not app.sqlite)
RESTORED_BROWSER_DECKS = "restored-browser-decks.json"
SYNCED_BROWSER_DECKS = "browser-decks.json"  # the host browser's latest copy, so automatic backups carry My decks too  # after a restore: waiting for the host's browser to take them back
MAX_BROWSER_DECKS_BYTES = 32 * 1024 * 1024
ASSET_NAME = re.compile(r"^assets/[0-9a-f]{64}\.(png|jpg|jpeg|webp)$")
MAX_BACKUP_BYTES = 2 * 1024 * 1024 * 1024
MAX_ART_BYTES = 3_000_000  # one image in a backup (like a deck's art sent over the LAN, app/multiplayer/lan_art.py)
ART_HEADROOM = 16 * 1024 * 1024  # art stops this far below MAX_BACKUP_BYTES (the manifest, rounding)
ART_NAME = re.compile(r"^images/(cards|tokens)/([0-9a-f]{2})/([0-9a-f-]{36})-(\d)-([a-z_]+)\.jpg$")
SYMBOL_NAME = re.compile(r"^images/symbols/[A-Z0-9]{1,16}\.svg$")
CARD_BACK_NAME = f"images/backs/{CARD_BACK_ID}-normal.jpg"
SYMBOL_INDEX_NAME = f"images/symbols/{SYMBOL_INDEX}"
KEEP_BACKUPS = 12  # backups the host made by hand
KEEP_AUTO_RECENT = 8  # automatic ones: the newest few …
KEEP_AUTO_DAYS = 7  # … plus the last one of each of the past week's days


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


def browser_decks_blob(decks: Any) -> bytes:
    """The host browser's "My decks", checked: a JSON list of objects, within the size limit."""
    if not isinstance(decks, list) or not all(isinstance(d, dict) for d in decks):
        raise BackupError("My decks must be a list")
    blob = json.dumps(decks).encode()
    if len(blob) > MAX_BROWSER_DECKS_BYTES:
        raise BackupError("My decks are too large to back up")
    return blob


def is_art_name(name: str) -> bool:
    """A name in a backup that may hold art: exactly the image cache's own layout (never a path, a stray name, or a
    prefix folder that doesn't match the id, which ``ImageStore.find`` would never look in)."""
    if name in (CARD_BACK_NAME, SYMBOL_INDEX_NAME) or SYMBOL_NAME.match(name):
        return True
    m = ART_NAME.match(name)
    if not m:
        return False
    _kind, prefix, card_id, face, size = m.groups()
    return bool(UUID_RE.match(card_id)) and prefix == card_id[:2] and int(face) < MAX_FACES and size in IMAGE_SIZES


def _art_ok(name: str, body: bytes) -> bool:
    """An art file's content: a JPEG, a plain SVG (nothing active), a symbol list that is a JSON object."""
    from app.cards.linked import is_plain_svg  # (here: keeps the storage module light to import)

    if len(body) > MAX_ART_BYTES:
        return False
    if name.endswith(".jpg"):
        return body.startswith(b"\xff\xd8\xff")
    if name.endswith(".svg"):
        return is_plain_svg(body)
    try:
        return isinstance(json.loads(body), dict)
    except (ValueError, UnicodeDecodeError):
        return False


def deck_art(images: ImageStore, printing_ids: list[str]) -> list[tuple[Path, str]]:
    """The cached art for these printings (every cached face and size, either kind), the card back and the mana
    symbols, as ``(file, name in the backup)``. Only the cache: the installer's bundled images are on every copy."""
    root = images.root
    out: list[tuple[Path, str]] = []
    for card_id in dict.fromkeys(printing_ids):
        if not UUID_RE.match(card_id):
            continue
        for kind in ("cards", "tokens"):
            folder = root / kind / card_id[:2]
            if folder.is_dir():
                out += [(f, f"images/{kind}/{card_id[:2]}/{f.name}") for f in sorted(folder.glob(f"{card_id}-*.jpg"))
                        if f.is_file() and is_art_name(f"images/{kind}/{card_id[:2]}/{f.name}")]
    back = images.card_back()
    if back is not None:
        out.append((back, CARD_BACK_NAME))
    codes = sorted({e["svg"] for e in images.symbol_index().values()})
    if codes:
        out.append((images.symbols_dir() / SYMBOL_INDEX, SYMBOL_INDEX_NAME))
        for code in codes:
            path = images.symbol_path(code)
            if path.is_file():
                out.append((path, f"images/symbols/{code}.svg"))
    return out


def create_backup(data_dir: Path, conn: sqlite3.Connection, lock: Any, assets_dir: Path, *, reason: str | None = None,
                  copy_dir: Path | None = None, browser_decks: list[Any] | None = None,
                  art: list[tuple[Path, str]] | None = None) -> dict[str, Any]:
    """A backup made by hand, or an automatic one when ``reason`` says why ("start-up", "after a recorded game" …).
    ``browser_decks``: the "My decks" of the browser that asked for the backup (they live in browser storage, so the
    database alone would leave them behind when the pod moves to another computer). ``art``: ``deck_art(...)``, the
    decks' card art for offline play (hand-made backups only), added while the backup stays under the size limit."""
    synced = data_dir / SYNCED_BROWSER_DECKS
    decks_blob = browser_decks_blob(browser_decks) if browser_decks is not None else synced.read_bytes() if synced.is_file() else None
    out_dir = backups_dir(data_dir)
    prefix = AUTO_PREFIX if reason else "fyodor-backup-"
    dest = _unique(out_dir / f"{prefix}{time.strftime('%Y%m%d-%H%M%S')}.zip")
    tmp_db = out_dir / ".backup-app.sqlite"
    with lock:
        copy_sqlite(conn, tmp_db)
    files = 0
    art_files = art_bytes = art_left_out = 0
    try:
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_db, "app.sqlite")
            total = tmp_db.stat().st_size
            if decks_blob is not None:
                zf.writestr(BROWSER_DECKS, decks_blob)
                total += len(decks_blob)
            if assets_dir.is_dir():
                for f in sorted(assets_dir.iterdir()):
                    if f.is_file() and ASSET_NAME.match(f"assets/{f.name}"):
                        zf.write(f, f"assets/{f.name}")
                        total += f.stat().st_size
                        files += 1
            for f, name in art or []:  # (a restore checks the unpacked total, so that is what the limit counts)
                try:
                    size = f.stat().st_size
                    if size > MAX_ART_BYTES or total + size > MAX_BACKUP_BYTES - ART_HEADROOM:
                        art_left_out += 1
                        continue
                    zf.write(f, name, compress_type=zipfile.ZIP_STORED)
                except OSError:  # gone meanwhile (an update replacing art): the rest still counts
                    continue
                total += size
                art_files += 1
                art_bytes += size
            if art_left_out:
                log.warning("Backup: %d art file(s) left out to stay under the size limit", art_left_out)
            manifest = {"format": "fyodor-backup", "version": 1, "app_version": __version__,
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "schema_version": schema_version(tmp_db),
                        "assets": files, "browser_decks": len(json.loads(decks_blob)) if decks_blob else 0,
                        "art": art_files, "art_bytes": art_bytes, **({"art_left_out": art_left_out} if art_left_out else {}),
                        **({"reason": reason} if reason else {})}
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    finally:
        tmp_db.unlink(missing_ok=True)
    for name in prune(list_backups(data_dir)):
        (out_dir / name).unlink(missing_ok=True)
    made = describe(dest)
    made.update(art=art_files, art_left_out=art_left_out)
    if copy_dir is not None:
        try:
            made["copied_to"] = copy_out(out_dir, copy_dir)
        except OSError as exc:  # the stick isn't plugged in: the backup itself still counts
            log.warning("Could not copy backups to %s: %s", copy_dir, exc)
            made["copy_error"] = f"Couldn't copy to {copy_dir}: {exc.strerror or exc}"
    return made


def prune(backups: list[dict[str, Any]], now: float | None = None) -> list[str]:
    """Names to delete (``backups`` newest first). Hand-made: the newest ``KEEP_BACKUPS``. Automatic, like a rotating
    autosave: the newest ``KEEP_AUTO_RECENT`` plus the newest of each of the last ``KEEP_AUTO_DAYS`` days, so a mistake
    noticed a few days later still has a backup from before it."""
    now = time.time() if now is None else now
    manual = [b for b in backups if not b["auto"]]
    auto = [b for b in backups if b["auto"]]
    drop = [b["name"] for b in manual[KEEP_BACKUPS:]]
    days_kept: set[str] = set()
    for i, b in enumerate(auto):
        day = time.strftime("%Y-%m-%d", time.localtime(b["mtime"]))
        recent_day = now - b["mtime"] < KEEP_AUTO_DAYS * 86400
        if i < KEEP_AUTO_RECENT or (recent_day and day not in days_kept):
            days_kept.add(day)
            continue
        drop.append(b["name"])
    return drop


def copy_out(out_dir: Path, copy_dir: Path) -> str:
    """Mirror the backups folder to a second place (a USB stick, a synced folder) so a dead disk doesn't take both."""
    copy_dir.mkdir(parents=True, exist_ok=True)
    keep = {f.name for f in out_dir.iterdir() if f.is_file() and BACKUP_NAME.match(f.name)}
    for name in sorted(keep):
        target = copy_dir / name
        if not target.exists():
            tmp = copy_dir / f".{name}.part"
            shutil.copyfile(out_dir / name, tmp)
            tmp.replace(target)
    for f in copy_dir.iterdir():
        if f.is_file() and BACKUP_NAME.match(f.name) and f.name not in keep:
            f.unlink(missing_ok=True)
    return str(copy_dir)


def _reason(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as zf:
            reason = json.loads(zf.read("manifest.json")).get("reason")
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None
    return reason if isinstance(reason, str) else None


def describe(path: Path) -> dict[str, Any]:
    st = path.stat()
    auto = path.name.startswith(AUTO_PREFIX)
    return {"name": path.name, "size": st.st_size, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime)),
            "mtime": st.st_mtime, "auto": auto, "reason": _reason(path) if auto else None}


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


def stage_restore(data_dir: Path, blob: bytes | Path) -> dict[str, Any]:
    """Validate a backup (an upload, or a listed file read from disk as it unpacks) and stage it; it is applied when
    Fyodor starts next."""
    size = blob.stat().st_size if isinstance(blob, Path) else len(blob)
    if size > MAX_BACKUP_BYTES:
        raise BackupError("Backup is too large")
    try:
        zf = zipfile.ZipFile(blob if isinstance(blob, Path) else io.BytesIO(blob))
    except (zipfile.BadZipFile, OSError) as exc:
        raise BackupError("Not a zip file") from exc
    with zf:
        names = zf.namelist()
        if "manifest.json" not in names or "app.sqlite" not in names:
            raise BackupError("Not a Fyodor backup (manifest.json or app.sqlite missing)")
        for info in zf.infolist():
            if info.is_dir():
                continue
            if (info.filename not in ("manifest.json", "app.sqlite", BROWSER_DECKS) and not ASSET_NAME.match(info.filename)
                    and not is_art_name(info.filename)):
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
        art = skipped = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = pending / info.filename  # names were checked against a strict allowlist above
            if info.filename.startswith("images/"):
                with zf.open(info) as src:
                    body = src.read(MAX_ART_BYTES + 1)
                if not _art_ok(info.filename, body):  # not what its name says: left out, the rest still restores
                    skipped += 1
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                art += 1
                continue
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
        if skipped:
            log.warning("Restore: %d art file(s) in the backup were not images and were left out", skipped)
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
    decks = pending / BROWSER_DECKS
    if decks.is_file():
        try:
            browser_decks_blob(json.loads(decks.read_bytes()))
        except (ValueError, BackupError) as exc:
            shutil.rmtree(pending, ignore_errors=True)
            raise BackupError("The decks list in this backup is damaged") from exc
    return {"staged": True, "created_at": manifest.get("created_at"), "app_version": manifest.get("app_version"),
            "restart_required": True, "browser_decks": decks.is_file(), "art": art}


def restore_pending(data_dir: Path) -> bool:
    """A restore is staged and waits for Fyodor to restart."""
    return (_pending_dir(data_dir) / "app.sqlite").is_file()


def take_restored_browser_decks(data_dir: Path, *, consume: bool) -> list[Any]:
    """The "My decks" that came with the last restore, for the host's browser to merge in (``consume``: then forget them)."""
    path = data_dir / RESTORED_BROWSER_DECKS
    if not path.is_file():
        return []
    try:
        decks = json.loads(path.read_bytes())
    except ValueError:
        decks = []
    if consume:
        path.unlink(missing_ok=True)
    return decks if isinstance(decks, list) else []


def apply_pending_restore(data_dir: Path, app_db: Path, assets_dir: Path, images_dir: Path | None = None) -> bool:
    """On start: swap a staged backup in (the current database is backed up first). Its art goes into the image cache
    (``images_dir``) only where the cache has none: newer art already on this computer stays."""
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
    staged_art = pending / "images"
    if images_dir is not None and staged_art.is_dir():
        for f in staged_art.rglob("*"):
            name = f.relative_to(pending).as_posix()
            if not f.is_file() or f.is_symlink() or not is_art_name(name):
                continue
            target = images_dir / name.removeprefix("images/")
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), target)
    decks = pending / BROWSER_DECKS
    if decks.is_file():
        shutil.move(str(decks), data_dir / RESTORED_BROWSER_DECKS)
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
