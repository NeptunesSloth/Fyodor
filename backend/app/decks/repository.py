"""Deck persistence in ``app.sqlite``."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime

from app.decks.models import Deck, DeckCategory, DeckEntry, DeckIn, DeckSource, Requested
from app.storage.db import transaction


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class DeckNotFound(LookupError):
    pass


class DeckRepository:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock) -> None:
        self.conn = conn
        self.lock = lock

    def list_all(self) -> list[Deck]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM decks ORDER BY updated_at DESC, name").fetchall()
            return [self._load(row) for row in rows]

    def get(self, deck_id: str) -> Deck:
        with self.lock:
            row = self.conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
            if row is None:
                raise DeckNotFound(deck_id)
            return self._load(row)

    def create(self, deck: DeckIn, *, source: DeckSource | None = None,
               snapshot: list[DeckEntry] | None = None) -> Deck:
        deck_id = uuid.uuid4().hex
        now = _now()
        with self.lock, transaction(self.conn):
            self.conn.execute(
                "INSERT INTO decks (id, name, format, notes, created_at, updated_at, categories, source, source_snapshot) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (deck_id, deck.name, deck.format, deck.notes, now, now, _categories_json(deck.categories),
                 source.model_dump_json() if source else None, _snapshot_json(snapshot)),
            )
            self._write_entries(deck_id, deck.entries)
        return self.get(deck_id)

    def update(self, deck_id: str, deck: DeckIn) -> Deck:
        with self.lock, transaction(self.conn):
            cur = self.conn.execute(
                "UPDATE decks SET name = ?, format = ?, notes = ?, categories = ?, updated_at = ? WHERE id = ?",
                (deck.name, deck.format, deck.notes, _categories_json(deck.categories), _now(), deck_id),
            )
            if cur.rowcount == 0:
                raise DeckNotFound(deck_id)
            self.conn.execute("DELETE FROM deck_cards WHERE deck_id = ?", (deck_id,))
            self._write_entries(deck_id, deck.entries)
        return self.get(deck_id)

    def set_source(self, deck_id: str, source: DeckSource | None, snapshot: list[DeckEntry] | None) -> None:
        with self.lock, transaction(self.conn):
            cur = self.conn.execute(
                "UPDATE decks SET source = ?, source_snapshot = ? WHERE id = ?",
                (source.model_dump_json() if source else None, _snapshot_json(snapshot), deck_id),
            )
            if cur.rowcount == 0:
                raise DeckNotFound(deck_id)

    def delete(self, deck_id: str) -> None:
        with self.lock, transaction(self.conn):
            cur = self.conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
            if cur.rowcount == 0:
                raise DeckNotFound(deck_id)

    def _write_entries(self, deck_id: str, entries: list[DeckEntry]) -> None:
        self.conn.executemany(
            "INSERT INTO deck_cards (deck_id, position, section, quantity, name, printing_id, set_code, "
            "collector_number, is_commander, oracle_id, finish, categories, tags, resolution, requested) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (deck_id, i, e.section, e.quantity, e.name, e.printing_id, e.set_code, e.collector_number,
                 1 if e.section == "commander" else 0, e.oracle_id, e.finish, json.dumps(e.categories),
                 json.dumps(e.tags), e.resolution, e.requested.model_dump_json() if e.requested else None)
                for i, e in enumerate(entries)
            ],
        )

    def _load(self, row: sqlite3.Row) -> Deck:
        cards = self.conn.execute(
            "SELECT * FROM deck_cards WHERE deck_id = ? ORDER BY position", (row["id"],)
        ).fetchall()
        return Deck(
            id=row["id"],
            name=row["name"],
            format=row["format"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            categories=[DeckCategory(**c) for c in json.loads(row["categories"] or "[]")],
            source=DeckSource.model_validate_json(row["source"]) if row["source"] else None,
            source_snapshot=[DeckEntry(**e) for e in json.loads(row["source_snapshot"])] if row["source_snapshot"] else None,
            entries=[_entry(c) for c in cards],
        )


def _entry(c: sqlite3.Row) -> DeckEntry:
    return DeckEntry(
        section=c["section"],
        quantity=c["quantity"],
        name=c["name"],
        printing_id=c["printing_id"],
        oracle_id=c["oracle_id"],
        set_code=c["set_code"],
        collector_number=c["collector_number"],
        finish=c["finish"] or "nonfoil",
        categories=json.loads(c["categories"] or "[]"),
        tags=json.loads(c["tags"] or "[]"),
        resolution=c["resolution"],
        requested=Requested.model_validate_json(c["requested"]) if c["requested"] else None,
    )


def _categories_json(categories: list[DeckCategory]) -> str:
    return json.dumps([c.model_dump() for c in categories])


def _snapshot_json(snapshot: list[DeckEntry] | None) -> str | None:
    return json.dumps([e.model_dump() for e in snapshot]) if snapshot is not None else None
