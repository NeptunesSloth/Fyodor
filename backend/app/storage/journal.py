"""Game-night recovery: live rooms, a per-change journal, and client action ids.

A started table is stored as its room metadata (mode, room code, seats and their tokens, host
seat, password hash) plus a *checkpoint* (the latest autosave) and a *journal* of every change
applied since then (resolved actions, undo, redo). If the host computer crashes or Fyodor is
restarted, the table is rebuilt from the checkpoint and the journal is replayed; players
reconnect with the seat tokens their browsers already hold and are back in their seats.

Client action ids make retries safe: an action sent twice (a flaky connection, a reconnect) is
applied once; the second copy is answered ALREADY_APPLIED.

These rows live in app.sqlite on the host computer only; nothing here is ever sent to clients.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.storage.db import transaction

MAX_CLIENT_ACTIONS = 512  # remembered per table


@dataclass
class LiveRoom:
    game_id: str
    meta: dict[str, Any]
    checkpoint: str | None
    entries: list[dict[str, Any]]
    client_actions: dict[str, str]


class RoomJournal:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock) -> None:
        self.conn = conn
        self.lock = lock

    def save_meta(self, game_id: str, meta: dict[str, Any]) -> None:
        with self.lock, transaction(self.conn):
            self.conn.execute(
                "INSERT INTO live_rooms (game_id, meta, checkpoint, updated_at) VALUES (?, ?, NULL, ?) "
                "ON CONFLICT(game_id) DO UPDATE SET meta = excluded.meta, updated_at = excluded.updated_at",
                (game_id, json.dumps(meta), time.time()),
            )

    def append(self, game_id: str, entry: dict[str, Any]) -> None:
        with self.lock, transaction(self.conn):
            row = self.conn.execute("SELECT COALESCE(MAX(seq), 0) AS n FROM room_journal WHERE game_id = ?", (game_id,)).fetchone()
            self.conn.execute("INSERT INTO room_journal (game_id, seq, entry) VALUES (?, ?, ?)",
                              (game_id, int(row["n"]) + 1, json.dumps(entry)))

    def checkpoint(self, game_id: str, save_id: str) -> None:
        """A fresh autosave holds everything so far: point at it and drop the journal."""
        with self.lock, transaction(self.conn):
            self.conn.execute("UPDATE live_rooms SET checkpoint = ?, updated_at = ? WHERE game_id = ?", (save_id, time.time(), game_id))
            self.conn.execute("DELETE FROM room_journal WHERE game_id = ?", (game_id,))

    def forget(self, game_id: str) -> None:
        with self.lock, transaction(self.conn):
            for table in ("live_rooms", "room_journal", "client_actions"):
                self.conn.execute(f"DELETE FROM {table} WHERE game_id = ?", (game_id,))  # noqa: S608 - fixed names

    def live(self) -> list[LiveRoom]:
        with self.lock:
            rooms = self.conn.execute("SELECT game_id, meta, checkpoint FROM live_rooms ORDER BY updated_at").fetchall()
            out = []
            for r in rooms:
                entries = [json.loads(e["entry"]) for e in self.conn.execute(
                    "SELECT entry FROM room_journal WHERE game_id = ? ORDER BY seq", (r["game_id"],))]
                acts = {a["client_action_id"]: a["outcome"] for a in self.conn.execute(
                    "SELECT client_action_id, outcome FROM client_actions WHERE game_id = ? ORDER BY created_at", (r["game_id"],))}
                out.append(LiveRoom(r["game_id"], json.loads(r["meta"]), r["checkpoint"], entries, acts))
            return out

    def remember_action(self, game_id: str, client_action_id: str, outcome: str) -> None:
        with self.lock, transaction(self.conn):
            self.conn.execute(
                "INSERT OR REPLACE INTO client_actions (game_id, client_action_id, outcome, created_at) VALUES (?, ?, ?, ?)",
                (game_id, client_action_id, outcome[:300], time.time()),
            )
            self.conn.execute(
                "DELETE FROM client_actions WHERE game_id = ? AND client_action_id NOT IN "
                "(SELECT client_action_id FROM client_actions WHERE game_id = ? ORDER BY created_at DESC LIMIT ?)",
                (game_id, game_id, MAX_CLIENT_ACTIONS),
            )
