"""-- Teach Fyodor -- the host's library of taught mechanics and card lines (app.sqlite table ``taught``, migration 12; in every backup).

Each row holds one entry (``app.rules.taught.clean_entry``: pieces and values from the vocabulary, never code). The enabled entries
are what new games start with (``taught.set_library``); a game in progress keeps its own copy. Shared files ("fyodor-teach" JSON)
are checked as strictly as a new entry: an unknown field, piece or value refuses the whole file.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from app.rules import taught
from app.storage.db import locked, transaction

MAX_FILE_BYTES = 512 * 1024


class TaughtNotFound(LookupError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


match_key = taught.match_key_of


class TaughtRepository:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock) -> None:
        self.conn = conn
        self.lock = lock
        self.publish()

    def _public(self, row: sqlite3.Row) -> dict[str, Any]:
        entry = json.loads(row["entry"])
        return {"id": row["id"], "kind": row["kind"], "name": row["name"], "oracle_id": row["oracle_id"], "line": row["line"],
                "enabled": bool(row["enabled"]), "entry": entry, "lines": taught.compile_entry(entry),
                "updated_at": row["updated_at"]}

    @locked
    def list_all(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM taught ORDER BY kind DESC, name COLLATE NOCASE").fetchall()
        return [self._public(r) for r in rows]

    @locked
    def get(self, entry_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM taught WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise TaughtNotFound(entry_id)
        return self._public(row)

    @locked
    def enabled(self) -> list[dict[str, Any]]:
        return [json.loads(r["entry"]) for r in self.conn.execute("SELECT entry FROM taught WHERE enabled = 1 ORDER BY created_at, id")]

    def publish(self) -> None:
        """New games start with the enabled entries."""
        taught.set_library(self.enabled())

    def _write(self, entry: dict[str, Any], *, entry_id: str | None, enabled: bool | None) -> str:
        """Insert or update one checked entry (inside a transaction). The same keyword / line replaces the older one."""
        key = match_key(entry)
        now = _now()
        clash = self.conn.execute("SELECT id FROM taught WHERE match_key = ?", (key,)).fetchone()
        if entry_id is None and clash is not None:
            entry_id = clash["id"]
        elif entry_id is not None and clash is not None and clash["id"] != entry_id:
            raise ValueError(f"{entry['name']} is already taught: edit that one instead")
        body = json.dumps(entry, sort_keys=True)
        if entry_id is not None and self.conn.execute("SELECT 1 FROM taught WHERE id = ?", (entry_id,)).fetchone():
            self.conn.execute("UPDATE taught SET kind = ?, name = ?, oracle_id = ?, line = ?, match_key = ?, entry = ?, updated_at = ?"
                              + (", enabled = ?" if enabled is not None else "") + " WHERE id = ?",
                              (entry["kind"], entry["name"], entry.get("oracle_id"), entry.get("line"), key, body, now,
                               *((int(enabled),) if enabled is not None else ()), entry_id))
            return entry_id
        if entry_id is not None:
            raise TaughtNotFound(entry_id)
        if self.conn.execute("SELECT COUNT(*) FROM taught").fetchone()[0] >= taught.MAX_ENTRIES:
            raise ValueError("The taught library is full")
        new_id = uuid.uuid4().hex[:16]
        self.conn.execute("INSERT INTO taught (id, kind, name, oracle_id, line, match_key, enabled, entry, created_at, updated_at) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (new_id, entry["kind"], entry["name"], entry.get("oracle_id"), entry.get("line"), key,
                           int(True if enabled is None else enabled), body, now, now))
        return new_id

    @staticmethod
    def checked(raw: Any) -> dict[str, Any]:
        """The entry rebuilt from the vocabulary, and only if the engine reads every ability it makes."""
        result = taught.check(raw)
        if not result["ok"]:
            raise ValueError(result["problems"][0]["message"] if result["problems"] else "Fyodor can't read this yet")
        return result["entry"]  # type: ignore[no-any-return]

    def save(self, raw: Any, *, entry_id: str | None = None, enabled: bool | None = None) -> dict[str, Any]:
        entry = self.checked(raw)
        with self.lock, transaction(self.conn):
            saved = self._write(entry, entry_id=entry_id, enabled=enabled)
        self.publish()
        return self.get(saved)

    def set_enabled(self, entry_id: str, enabled: bool) -> dict[str, Any]:
        with self.lock, transaction(self.conn):
            if self.conn.execute("UPDATE taught SET enabled = ?, updated_at = ? WHERE id = ?", (int(enabled), _now(), entry_id)).rowcount == 0:
                raise TaughtNotFound(entry_id)
        self.publish()
        return self.get(entry_id)

    def delete(self, entry_id: str) -> None:
        with self.lock, transaction(self.conn):
            if self.conn.execute("DELETE FROM taught WHERE id = ?", (entry_id,)).rowcount == 0:
                raise TaughtNotFound(entry_id)
        self.publish()

    # -- sharing ------------------------------------------------------------------------------------------------------
    def export(self, ids: list[str] | None = None) -> dict[str, Any]:
        rows = self.list_all()
        return {"format": taught.FORMAT, "version": taught.FORMAT_VERSION,
                "entries": [r["entry"] for r in rows if ids is None or r["id"] in ids]}

    @staticmethod
    def read_file(data: Any) -> list[dict[str, Any]]:
        """A shared file's entries, each checked like a new one; anything unexpected refuses the whole file."""
        if not isinstance(data, dict) or set(data) != {"format", "version", "entries"}:
            raise ValueError("Not a Teach Fyodor file")
        if data["format"] != taught.FORMAT:
            raise ValueError("Not a Teach Fyodor file")
        if data["version"] != taught.FORMAT_VERSION:
            raise ValueError("This file was made by a different version of Fyodor")
        entries = data["entries"]
        if not isinstance(entries, list) or not entries or len(entries) > taught.MAX_ENTRIES:
            raise ValueError("The file has no taught entries")
        out = []
        for i, raw in enumerate(entries, start=1):
            try:
                out.append(TaughtRepository.checked(raw))
            except ValueError as exc:
                name = raw.get("name") if isinstance(raw, dict) and isinstance(raw.get("name"), str) else f"entry {i}"
                raise ValueError(f"{str(name)[:60]}: {exc}") from None
        keys = [match_key(e) for e in out]
        if len(set(keys)) != len(keys):
            raise ValueError("The file teaches the same thing twice")
        return out

    def import_file(self, data: Any) -> dict[str, Any]:
        entries = self.read_file(data)
        replaced = 0
        with self.lock, transaction(self.conn):
            for entry in entries:
                if self.conn.execute("SELECT 1 FROM taught WHERE match_key = ?", (match_key(entry),)).fetchone():
                    replaced += 1
                self._write(entry, entry_id=None, enabled=None)
        self.publish()
        return {"imported": len(entries) - replaced, "replaced": replaced, "entries": self.list_all()}
