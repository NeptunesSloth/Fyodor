"""The macro library: per-card macros (keyed by oracle id, so every printing shares them) and a
personal library. Definitions are declarative JSON (see game/macros.py), stored with a version."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from app.game.macros import MacroDef
from app.storage.db import transaction

MAX_MACROS = 1000


class MacroNotFound(LookupError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def load_definition(raw: str) -> MacroDef:
    """Parse a stored definition, upgrading older versions (currently only version 1 exists)."""
    data = json.loads(raw)
    data.setdefault("version", 1)
    return MacroDef.model_validate(data)


class MacroRepository:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock) -> None:
        self.conn = conn
        self.lock = lock

    def _public(self, row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "scope": row["scope"], "oracle_id": row["oracle_id"], "name": row["name"],
                "definition": load_definition(row["definition"]).model_dump(), "updated_at": row["updated_at"]}

    def list_all(self, oracle_id: str | None = None) -> list[dict[str, Any]]:
        if oracle_id:
            rows = self.conn.execute(
                "SELECT * FROM macros WHERE (scope = 'card' AND oracle_id = ?) OR scope = 'library' ORDER BY scope, name",
                (oracle_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM macros ORDER BY scope, name").fetchall()
        return [self._public(r) for r in rows]

    def get(self, macro_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM macros WHERE id = ?", (macro_id,)).fetchone()
        if row is None:
            raise MacroNotFound(macro_id)
        return self._public(row)

    def save(self, definition: MacroDef, *, scope: str, oracle_id: str | None, macro_id: str | None = None) -> dict[str, Any]:
        if scope not in ("card", "library") or (scope == "card" and not oracle_id):
            raise ValueError("A card macro needs a card")
        now = _now()
        body = definition.model_dump_json()
        with self.lock, transaction(self.conn):
            if macro_id:
                if self.conn.execute("UPDATE macros SET name = ?, definition = ?, scope = ?, oracle_id = ?, updated_at = ? WHERE id = ?",
                                     (definition.name, body, scope, oracle_id if scope == "card" else None, now, macro_id)).rowcount == 0:
                    raise MacroNotFound(macro_id)
            else:
                if self.conn.execute("SELECT COUNT(*) FROM macros").fetchone()[0] >= MAX_MACROS:
                    raise ValueError("The macro library is full")
                macro_id = uuid.uuid4().hex[:16]
                self.conn.execute(
                    "INSERT INTO macros (id, scope, oracle_id, name, definition, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (macro_id, scope, oracle_id if scope == "card" else None, definition.name, body, now, now))
        return self.get(macro_id)

    def delete(self, macro_id: str) -> None:
        with self.lock, transaction(self.conn):
            if self.conn.execute("DELETE FROM macros WHERE id = ?", (macro_id,)).rowcount == 0:
                raise MacroNotFound(macro_id)

    def export(self) -> list[dict[str, Any]]:
        return self.list_all()
