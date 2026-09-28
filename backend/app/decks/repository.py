"""Deck persistence in ``app.sqlite``."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime

from app.decks.models import Deck, DeckEntry, DeckIn
from app.storage.db import transaction


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class DeckNotFound(LookupError):
    pass


class DeckRepository:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock) -> None:
        self.conn = conn
        self.lock = lock

    def list(self) -> list[Deck]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM decks ORDER BY updated_at DESC, name").fetchall()
            return [self._load(row) for row in rows]

    def get(self, deck_id: str) -> Deck:
        with self.lock:
            row = self.conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
            if row is None:
                raise DeckNotFound(deck_id)
            return self._load(row)

    def create(self, deck: DeckIn) -> Deck:
        deck_id = uuid.uuid4().hex
        now = _now()
        with self.lock, transaction(self.conn):
            self.conn.execute(
                "INSERT INTO decks (id, name, format, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (deck_id, deck.name, deck.format, deck.notes, now, now),
            )
            self._write_entries(deck_id, deck.entries)
        return self.get(deck_id)

    def update(self, deck_id: str, deck: DeckIn) -> Deck:
        with self.lock, transaction(self.conn):
            cur = self.conn.execute(
                "UPDATE decks SET name = ?, format = ?, notes = ?, updated_at = ? WHERE id = ?",
                (deck.name, deck.format, deck.notes, _now(), deck_id),
            )
            if cur.rowcount == 0:
                raise DeckNotFound(deck_id)
            self.conn.execute("DELETE FROM deck_cards WHERE deck_id = ?", (deck_id,))
            self._write_entries(deck_id, deck.entries)
        return self.get(deck_id)

    def delete(self, deck_id: str) -> None:
        with self.lock, transaction(self.conn):
            cur = self.conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
            if cur.rowcount == 0:
                raise DeckNotFound(deck_id)

    def _write_entries(self, deck_id: str, entries: list[DeckEntry]) -> None:
        self.conn.executemany(
            "INSERT INTO deck_cards (deck_id, position, section, quantity, name, printing_id, set_code, "
            "collector_number, is_commander) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (deck_id, i, e.section, e.quantity, e.name, e.printing_id, e.set_code, e.collector_number,
                 1 if e.section == "commander" else 0)
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
            entries=[
                DeckEntry(
                    section=c["section"],
                    quantity=c["quantity"],
                    name=c["name"],
                    printing_id=c["printing_id"],
                    set_code=c["set_code"],
                    collector_number=c["collector_number"],
                )
                for c in cards
            ],
        )
