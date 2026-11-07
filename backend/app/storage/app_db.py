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
    # 3: Archidekt-grade deck metadata (stable identities, finishes, categories, source link)
    """
    ALTER TABLE deck_cards ADD COLUMN oracle_id TEXT;
    ALTER TABLE deck_cards ADD COLUMN finish TEXT NOT NULL DEFAULT 'nonfoil';
    ALTER TABLE deck_cards ADD COLUMN categories TEXT NOT NULL DEFAULT '[]';
    ALTER TABLE deck_cards ADD COLUMN tags TEXT NOT NULL DEFAULT '[]';
    ALTER TABLE deck_cards ADD COLUMN resolution TEXT;
    ALTER TABLE deck_cards ADD COLUMN requested TEXT;
    ALTER TABLE decks ADD COLUMN categories TEXT NOT NULL DEFAULT '[]';
    ALTER TABLE decks ADD COLUMN source TEXT;
    ALTER TABLE decks ADD COLUMN source_snapshot TEXT;
    """,
    # 4: card macros (per card = by oracle id, and the personal library)
    """
    CREATE TABLE macros (
        id TEXT PRIMARY KEY,
        scope TEXT NOT NULL CHECK (scope IN ('card', 'library')),
        oracle_id TEXT,
        name TEXT NOT NULL,
        definition TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX macros_oracle ON macros(oracle_id);
    """,
    # 5: pod win tracker. Recorded results are the source of truth; stats are always recomputed.
    """
    CREATE TABLE pod_players (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        name_key TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    );
    CREATE TABLE game_results (
        id TEXT PRIMARY KEY,
        game_id TEXT NOT NULL UNIQUE,
        result_type TEXT NOT NULL CHECK (result_type IN ('single', 'multiple', 'draw', 'no_result')),
        table_name TEXT NOT NULL DEFAULT '',
        format TEXT NOT NULL DEFAULT '',
        started_at TEXT,
        recorded_at TEXT NOT NULL,
        duration_seconds INTEGER,
        turns INTEGER,
        notes TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE game_result_players (
        result_id TEXT NOT NULL REFERENCES game_results(id) ON DELETE CASCADE,
        seat TEXT NOT NULL,
        player_id TEXT NOT NULL REFERENCES pod_players(id),
        player_name TEXT NOT NULL,
        deck_key TEXT,
        deck_name TEXT,
        commanders TEXT NOT NULL DEFAULT '[]',
        outcome TEXT NOT NULL CHECK (outcome IN ('win', 'loss', 'draw', 'none')),
        PRIMARY KEY (result_id, seat)
    );
    CREATE INDEX grp_player ON game_result_players(player_id);
    """,
    # 6: managed custom assets (playmats, card backs, …). Files live in data/assets/<sha256>.<ext>.
    """
    CREATE TABLE assets (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        name TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        mime TEXT NOT NULL,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        size INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX assets_kind ON assets(kind, name);
    CREATE INDEX assets_sha ON assets(sha256);
    """,
    # 7: game-night recovery. A live table's room (code, seats and their tokens) and a journal of
    # every change since its last checkpoint (autosave), so a crash loses nothing and players
    # reconnect to the same seats. Local secrets on the host computer, never sent to clients.
    """
    CREATE TABLE live_rooms (
        game_id TEXT PRIMARY KEY,
        meta TEXT NOT NULL,
        checkpoint TEXT,
        updated_at REAL NOT NULL
    );
    CREATE TABLE room_journal (
        game_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        entry TEXT NOT NULL,
        PRIMARY KEY (game_id, seq)
    );
    CREATE TABLE client_actions (
        game_id TEXT NOT NULL,
        client_action_id TEXT NOT NULL,
        outcome TEXT NOT NULL,
        created_at REAL NOT NULL,
        PRIMARY KEY (game_id, client_action_id)
    );
    """,
    # 8: Fyodor is Commander-only. Decks saved as Constructed or Sandbox become Commander decks (their cards are kept).
    """
    UPDATE decks SET format = 'commander' WHERE format <> 'commander';
    """,
    # 9: -- pod history -- each recorded game keeps its elimination order and a compact, public final board (JSON; older
    # results have neither)
    """
    ALTER TABLE game_results ADD COLUMN eliminations TEXT NOT NULL DEFAULT '[]';
    ALTER TABLE game_results ADD COLUMN final_board TEXT NOT NULL DEFAULT '[]';
    """,
    # 10: -- deck folders -- the shelf groups decks into folders ('' = not in a folder)
    """
    ALTER TABLE decks ADD COLUMN folder TEXT NOT NULL DEFAULT '';
    """,
]


def open_app_db(path: Path | str) -> sqlite3.Connection:
    conn = connect(path)
    migrate(conn, MIGRATIONS, name="app")
    return conn
