"""Managed custom assets: one tidy place for playmats, card backs and other table images.

Files are stored by content hash (``data/assets/<sha256>.<ext>``) so identical uploads share a
file and every URL is immutable — LAN clients cache them forever. Clients only ever refer to
an asset by its opaque id; paths are never taken from requests.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.assets.validate import ImageInfo, sniff
from app.storage.db import locked, transaction

AssetKind = Literal["playmat", "card_back", "token_art", "counter_art", "utility", "reference", "dice_skin", "table_preset"]
KINDS: tuple[str, ...] = ("playmat", "card_back", "token_art", "counter_art", "utility", "reference", "dice_skin", "table_preset")
EXT = {"png": "png", "jpeg": "jpg", "webp": "webp"}
MAX_ASSETS = 2000


class AssetNotFound(LookupError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class AssetStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock, root: Path) -> None:
        self.conn = conn
        self.lock = lock
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    # -- files -----------------------------------------------------------------------
    def _file(self, sha: str, mime: str) -> Path:
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise AssetNotFound(sha)
        return self.root / f"{sha}.{ext}"

    def _write(self, data: bytes, info: ImageInfo) -> str:
        sha = hashlib.sha256(data).hexdigest()
        path = self._file(sha, info.mime)
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return sha

    def _gc(self, sha: str, mime: str) -> None:
        if not self.conn.execute("SELECT 1 FROM assets WHERE sha256 = ?", (sha,)).fetchone():
            self._file(sha, mime).unlink(missing_ok=True)

    @locked
    def path(self, asset_id: str) -> tuple[Path, str, str]:
        """(file path, mime, sha) for serving; raises AssetNotFound."""
        row = self._row(asset_id)
        return self._file(row["sha256"], row["mime"]), row["mime"], row["sha256"]

    # -- records ---------------------------------------------------------------------
    @locked
    def _row(self, asset_id: str) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            raise AssetNotFound(asset_id)
        return row

    @staticmethod
    def _public(row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "kind": row["kind"], "name": row["name"], "sha256": row["sha256"], "mime": row["mime"],
                "width": row["width"], "height": row["height"], "size": row["size"], "created_at": row["created_at"],
                "updated_at": row["updated_at"], "url": f"/api/assets/{row['id']}/file?v={row['sha256'][:12]}"}

    @locked
    def get(self, asset_id: str) -> dict[str, Any]:
        return self._public(self._row(asset_id))

    @locked
    def list(self, kind: str | None = None) -> list[dict[str, Any]]:
        if kind:
            rows = self.conn.execute("SELECT * FROM assets WHERE kind = ? ORDER BY name COLLATE NOCASE", (kind,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM assets ORDER BY kind, name COLLATE NOCASE").fetchall()
        return [self._public(r) for r in rows]

    def add(self, data: bytes, *, kind: str, name: str) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValueError(f"Unknown asset type {kind!r}")
        info = sniff(data)
        with self.lock, transaction(self.conn):
            if self.conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0] >= MAX_ASSETS:
                raise ValueError("The asset library is full; delete some assets first")
            sha = self._write(data, info)
            aid = uuid.uuid4().hex[:16]
            now = _now()
            self.conn.execute(
                "INSERT INTO assets (id, kind, name, sha256, mime, width, height, size, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (aid, kind, name, sha, info.mime, info.width, info.height, len(data), now, now),
            )
        return self.get(aid)

    def import_image(self, data: bytes, *, kind: str, name: str) -> tuple[dict[str, Any], bool]:
        """Add an image from a package, reusing an existing asset with the same content and kind.
        Returns (asset, created)."""
        sniff(data)  # validate the content before looking anything up
        sha = hashlib.sha256(data).hexdigest()
        with self.lock:
            row = self.conn.execute("SELECT id FROM assets WHERE sha256 = ? AND kind = ? ORDER BY rowid LIMIT 1", (sha, kind)).fetchone()
        if row is not None:
            return self.get(row["id"]), False
        return self.add(data, kind=kind, name=name), True

    def replace(self, asset_id: str, data: bytes) -> dict[str, Any]:
        info = sniff(data)
        with self.lock, transaction(self.conn):
            old = self._row(asset_id)
            sha = self._write(data, info)
            self.conn.execute(
                "UPDATE assets SET sha256 = ?, mime = ?, width = ?, height = ?, size = ?, updated_at = ? WHERE id = ?",
                (sha, info.mime, info.width, info.height, len(data), _now(), asset_id),
            )
            self._gc(old["sha256"], old["mime"])
        return self.get(asset_id)

    def rename(self, asset_id: str, name: str) -> dict[str, Any]:
        with self.lock, transaction(self.conn):
            self._row(asset_id)
            self.conn.execute("UPDATE assets SET name = ?, updated_at = ? WHERE id = ?", (name, _now(), asset_id))
        return self.get(asset_id)

    def duplicate(self, asset_id: str) -> dict[str, Any]:
        with self.lock, transaction(self.conn):
            row = self._row(asset_id)
            aid = uuid.uuid4().hex[:16]
            now = _now()
            self.conn.execute(
                "INSERT INTO assets (id, kind, name, sha256, mime, width, height, size, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (aid, row["kind"], f"{row['name']} (copy)", row["sha256"], row["mime"], row["width"], row["height"], row["size"], now, now),
            )
        return self.get(aid)

    def delete(self, asset_id: str) -> None:
        with self.lock, transaction(self.conn):
            row = self._row(asset_id)
            self.conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
            self._gc(row["sha256"], row["mime"])

    def read(self, asset_id: str) -> tuple[bytes, dict[str, Any]]:
        path, _mime, _sha = self.path(asset_id)
        return path.read_bytes(), self.get(asset_id)
