"""User data database (decks, saves). Separate from the rebuildable card database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.storage.db import connect, migrate

MIGRATIONS: list[str] = [
    # 1: decks
    """
    CREATE TABLE decks (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        format TEXT NOT NULL DEFAULT 'commander',
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE deck_cards (
        deck_id TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        section TEXT NOT NULL,
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        name TEXT NOT NULL,
        printing_id TEXT,
        set_code TEXT,
        collector_number TEXT,
        is_commander INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (deck_id, position)
    );
    """,
    # 2: saves
    """
    CREATE TABLE saves (
        id TEXT PRIMARY KEY,
        game_id TEXT NOT NULL,
        name TEXT NOT NULL,
        is_autosave INTEGER NOT NULL DEFAULT 0,
        format_version INTEGER NOT NULL,
        summary TEXT NOT NULL DEFAULT '{}',
        payload BLOB NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX saves_game ON saves(game_id, created_at);
    """,
]


def open_app_db(path: Path | str) -> sqlite3.Connection:
    conn = connect(path)
    migrate(conn, MIGRATIONS, name="app")
    return conn
