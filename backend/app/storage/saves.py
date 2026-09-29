"""Saved games in ``app.sqlite``."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from typing import Any

from app.game.errors import ActionError
from app.game.history import History
from app.game.state import GameState
from app.storage.db import transaction
from app.storage.save_format import SAVE_FORMAT, SAVE_VERSION, SaveFormatError, decode, encode

log = logging.getLogger(__name__)


class SaveNotFound(LookupError):
    pass


def _summary(state: GameState) -> dict[str, Any]:
    return {
        "game_name": state.name,
        "format": state.format,
        "turn": state.turn.number,
        "players": [{"name": p.name, "life": p.life, "deck": p.deck_name} for p in (state.players[i] for i in state.seat_order)],
    }


class SaveRepository:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock, *, keep_autosaves: int = 3) -> None:
        self.conn = conn
        self.lock = lock
        self.keep_autosaves = keep_autosaves

    def save(self, state: GameState, history: History | None, *, name: str, autosave: bool = False,
             extras: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "format": SAVE_FORMAT,
            "version": SAVE_VERSION,
            "saved_at": time.time(),
            "state": state.model_dump(mode="json"),
            "history": history.to_dict() if history else None,
            "extras": extras or {},  # e.g. named table snapshots
        }
        blob = encode(payload)
        save_id = uuid.uuid4().hex
        created = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        with self.lock, transaction(self.conn):
            self.conn.execute(
                "INSERT INTO saves (id, game_id, name, is_autosave, format_version, summary, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (save_id, state.id, name, 1 if autosave else 0, SAVE_VERSION, json.dumps(_summary(state)), blob, created),
            )
            if autosave:
                stale = self.conn.execute(
                    "SELECT id FROM saves WHERE game_id = ? AND is_autosave = 1 ORDER BY created_at DESC, rowid DESC LIMIT -1 OFFSET ?",
                    (state.id, self.keep_autosaves),
                ).fetchall()
                self.conn.executemany("DELETE FROM saves WHERE id = ?", [(r["id"],) for r in stale])
        return self.get_summary(save_id)

    def get_summary(self, save_id: str) -> dict[str, Any]:
        with self.lock:
            row = self.conn.execute(
                "SELECT id, game_id, name, is_autosave, format_version, summary, created_at, length(payload) AS size "
                "FROM saves WHERE id = ?",
                (save_id,),
            ).fetchone()
        if row is None:
            raise SaveNotFound(save_id)
        return self._row(row)

    def list_all(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, game_id, name, is_autosave, format_version, summary, created_at, length(payload) AS size "
                "FROM saves ORDER BY created_at DESC, rowid DESC"
            ).fetchall()
        return [self._row(r) for r in rows]

    def load(self, save_id: str, *, history_limit: int = 500) -> tuple[GameState, History | None]:
        with self.lock:
            row = self.conn.execute("SELECT payload FROM saves WHERE id = ?", (save_id,)).fetchone()
        if row is None:
            raise SaveNotFound(save_id)
        return load_payload(decode(row["payload"]), history_limit=history_limit)

    def extras(self, save_id: str) -> dict[str, Any]:
        """Things saved beside the game (named table snapshots)."""
        with self.lock:
            row = self.conn.execute("SELECT payload FROM saves WHERE id = ?", (save_id,)).fetchone()
        if row is None:
            raise SaveNotFound(save_id)
        extras = decode(row["payload"]).get("extras")
        return extras if isinstance(extras, dict) else {}

    def delete(self, save_id: str) -> None:
        with self.lock, transaction(self.conn):
            cur = self.conn.execute("DELETE FROM saves WHERE id = ?", (save_id,))
            if cur.rowcount == 0:
                raise SaveNotFound(save_id)

    def export_blob(self, save_id: str) -> bytes:
        with self.lock:
            row = self.conn.execute("SELECT payload FROM saves WHERE id = ?", (save_id,)).fetchone()
        if row is None:
            raise SaveNotFound(save_id)
        return bytes(row["payload"])

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "game_id": row["game_id"],
            "name": row["name"],
            "autosave": bool(row["is_autosave"]),
            "version": row["format_version"],
            "created_at": row["created_at"],
            "size": row["size"],
            **json.loads(row["summary"]),
        }


def load_payload(payload: dict[str, Any], *, history_limit: int = 500) -> tuple[GameState, History | None]:
    try:
        state = GameState.model_validate(payload["state"])
    except (KeyError, ValueError) as exc:
        raise SaveFormatError(f"Save contents are invalid: {exc}") from exc
    try:
        history = History.from_dict(payload["history"], limit=history_limit) if payload.get("history") else None
        replayed = history.state_at(history.cursor) if history is not None else None
    except (KeyError, ValueError, ActionError) as exc:
        # e.g. an action type that no longer exists: the table loads, only undo history is lost.
        log.warning("Dropping unreadable undo history from a save: %s", exc)
        history = replayed = None
    if history is not None and replayed is not None and replayed.model_dump(mode="json") != state.model_dump(mode="json"):
        if payload.get("migrated_from") and _core(replayed) == _core(state):
            # An upgraded save: the replay applies today's rules for bookkeeping fields
            # (e.g. view contexts) but the table itself is identical, so keep the history.
            state = replayed
        else:
            # History and snapshot disagree (should never happen); trust the snapshot.
            history = None
    return state, history


def _core(state: GameState) -> tuple[object, ...]:
    dump = state.model_dump(mode="json")
    return (dump["zones"], dump["players"], sorted(dump["cards"]), dump["turn"], dump["table"])
