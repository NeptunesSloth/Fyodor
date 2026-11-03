"""Pod win tracker: a lightweight, persistent history of our games.

Recorded results are the only source of truth. Games / wins / losses / win % are always
computed from them, so correcting or deleting a result can never leave the numbers wrong.
No private card data is stored — only who played, which deck, which commanders, and who won, plus (-- pod history --) the
order players went out and a public-only final board (``app.stats.recap``).
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from app.storage.db import locked, transaction

ResultType = Literal["single", "multiple", "draw", "no_result"]
Outcome = Literal["win", "loss", "draw", "none"]


class ResultError(ValueError):
    pass


class DuplicateResult(ResultError):
    pass


class ResultNotFound(LookupError):
    pass


@dataclass
class Participant:
    seat: str
    name: str
    deck_key: str | None = None
    deck_name: str | None = None
    commanders: list[str] = field(default_factory=list)


def name_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).casefold()


def deck_key_for(deck_id: str | None, deck_name: str | None, commanders: list[str]) -> str | None:
    """A stable local deck identity: the library deck id, else name + commanders."""
    if deck_id:
        return f"deck:{deck_id}"
    if deck_name or commanders:
        return "named:" + name_key(deck_name or "") + "|" + "|".join(sorted(name_key(c) for c in commanders))
    return None


def outcomes(result_type: ResultType, seats: list[str], winners: list[str]) -> dict[str, Outcome]:
    winners = list(dict.fromkeys(winners))
    if any(w not in seats for w in winners):
        raise ResultError("A winner must be one of the players")
    if result_type == "single":
        if len(winners) != 1:
            raise ResultError("Choose exactly one winner")
    elif result_type == "multiple":
        if len(winners) < 2:
            raise ResultError("Choose at least two winners (or use Single winner)")
        if len(winners) == len(seats):
            raise ResultError("Everyone can't win — use Draw")
    elif winners:
        raise ResultError("A draw or no-result game has no winners")
    if result_type == "draw":
        return {s: "draw" for s in seats}
    if result_type == "no_result":
        return {s: "none" for s in seats}
    return {s: ("win" if s in winners else "loss") for s in seats}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class PodStats:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock) -> None:
        self.conn = conn
        self.lock = lock

    # -- players ---------------------------------------------------------------------
    def _player_id(self, name: str) -> str:
        key = name_key(name)
        if not key:
            raise ResultError("Every player needs a name")
        row = self.conn.execute("SELECT id FROM pod_players WHERE name_key = ?", (key,)).fetchone()
        if row:
            self.conn.execute("UPDATE pod_players SET name = ? WHERE id = ?", (name.strip(), row["id"]))
            return str(row["id"])
        pid = uuid.uuid4().hex[:12]
        self.conn.execute("INSERT INTO pod_players (id, name, name_key, created_at) VALUES (?, ?, ?, ?)",
                          (pid, name.strip(), key, _now()))
        return pid

    # -- results ---------------------------------------------------------------------
    def record(self, *, game_id: str, result_type: ResultType, participants: list[Participant], winners: list[str],
               table_name: str = "", format: str = "", started_at: float | None = None, turns: int | None = None,
               notes: str = "", eliminations: list[dict[str, Any]] | None = None,
               final_board: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """``eliminations`` / ``final_board``: -- pod history -- the game's public record (``app.stats.recap``), if it has one."""
        if len(participants) < 1:
            raise ResultError("A game needs players")
        seats = [p.seat for p in participants]
        result = outcomes(result_type, seats, winners)
        now = datetime.now(UTC)
        started = datetime.fromtimestamp(started_at, UTC) if started_at else None
        rid = uuid.uuid4().hex[:16]
        with self.lock, transaction(self.conn):
            if self.conn.execute("SELECT 1 FROM game_results WHERE game_id = ?", (game_id,)).fetchone():
                raise DuplicateResult("This game's result is already recorded — correct it in Pod stats")
            self.conn.execute(
                "INSERT INTO game_results (id, game_id, result_type, table_name, format, started_at, recorded_at,"
                " duration_seconds, turns, notes, eliminations, final_board) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, game_id, result_type, table_name, format, started.isoformat(timespec="seconds") if started else None,
                 now.isoformat(timespec="seconds"), int((now - started).total_seconds()) if started else None, turns,
                 notes.strip(), json.dumps(eliminations or []), json.dumps(final_board or [])),
            )
            for p in participants:
                self.conn.execute(
                    "INSERT INTO game_result_players (result_id, seat, player_id, player_name, deck_key, deck_name,"
                    " commanders, outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (rid, p.seat, self._player_id(p.name), p.name.strip(), p.deck_key, p.deck_name,
                     json.dumps(p.commanders), result[p.seat]),
                )
        return self.get(rid)

    def edit(self, rid: str, *, result_type: ResultType | None = None, winners: list[str] | None = None,
             notes: str | None = None) -> dict[str, Any]:
        with self.lock, transaction(self.conn):
            current = self.get(rid)
            if result_type is not None or winners is not None:
                rtype = result_type or current["result_type"]
                win = winners if winners is not None else [p["seat"] for p in current["players"] if p["outcome"] == "win"]
                if rtype in ("draw", "no_result"):
                    win = []
                result = outcomes(rtype, [p["seat"] for p in current["players"]], win)
                self.conn.execute("UPDATE game_results SET result_type = ? WHERE id = ?", (rtype, rid))
                for seat, outcome in result.items():
                    self.conn.execute("UPDATE game_result_players SET outcome = ? WHERE result_id = ? AND seat = ?",
                                      (outcome, rid, seat))
            if notes is not None:
                self.conn.execute("UPDATE game_results SET notes = ? WHERE id = ?", (notes.strip(), rid))
        return self.get(rid)

    def delete(self, rid: str) -> None:
        with self.lock, transaction(self.conn):
            if self.conn.execute("DELETE FROM game_results WHERE id = ?", (rid,)).rowcount == 0:
                raise ResultNotFound(rid)

    @locked
    def get(self, rid: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM game_results WHERE id = ?", (rid,)).fetchone()
        if row is None:
            raise ResultNotFound(rid)
        return self._result(row)

    @locked
    def for_game(self, game_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM game_results WHERE game_id = ?", (game_id,)).fetchone()
        return self._result(row) if row else None

    def _result(self, row: sqlite3.Row) -> dict[str, Any]:
        players = [
            {"seat": p["seat"], "player_id": p["player_id"], "name": p["player_name"], "deck_key": p["deck_key"],
             "deck_name": p["deck_name"], "commanders": json.loads(p["commanders"]), "outcome": p["outcome"]}
            for p in self.conn.execute("SELECT * FROM game_result_players WHERE result_id = ? ORDER BY seat", (row["id"],))
        ]
        number = self.conn.execute(  # "Game #42": position in recording order
            "SELECT COUNT(*) FROM game_results WHERE rowid <= (SELECT rowid FROM game_results WHERE id = ?)",
            (row["id"],)).fetchone()[0]
        return {
            "id": row["id"], "number": number, "game_id": row["game_id"], "result_type": row["result_type"],
            "table_name": row["table_name"], "format": row["format"], "started_at": row["started_at"],
            "recorded_at": row["recorded_at"], "duration_seconds": row["duration_seconds"], "turns": row["turns"],
            "notes": row["notes"], "players": players,
            "winners": [p["name"] for p in players if p["outcome"] == "win"],
            # -- pod history -- who went out in which order, and the public final board (empty for older results)
            "eliminations": json.loads(row["eliminations"] or "[]"), "final_board": json.loads(row["final_board"] or "[]"),
        }

    @locked
    def history(self, *, limit: int = 100, player_id: str | None = None) -> list[dict[str, Any]]:
        if player_id:
            rows = self.conn.execute(
                "SELECT r.* FROM game_results r JOIN game_result_players p ON p.result_id = r.id WHERE p.player_id = ?"
                " ORDER BY r.rowid DESC LIMIT ?", (player_id, limit)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM game_results ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        return [self._result(r) for r in rows]

    # -- statistics (always computed from the results) -------------------------------
    _COUNTS = """
        SUM(CASE WHEN p.outcome != 'none' THEN 1 ELSE 0 END) AS games,
        SUM(CASE WHEN p.outcome = 'win' THEN 1 ELSE 0 END) AS wins,
        SUM(CASE WHEN p.outcome = 'loss' THEN 1 ELSE 0 END) AS losses,
        SUM(CASE WHEN p.outcome = 'draw' THEN 1 ELSE 0 END) AS draws
    """

    @staticmethod
    def _with_pct(row: dict[str, Any]) -> dict[str, Any]:
        games = row["games"] or 0
        row.update(games=games, wins=row["wins"] or 0, losses=row["losses"] or 0, draws=row["draws"] or 0)
        row["win_pct"] = round(100.0 * row["wins"] / games, 1) if games else None
        return row

    @locked
    def players(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            f"SELECT pl.id, pl.name, {self._COUNTS} FROM pod_players pl"
            " LEFT JOIN game_result_players p ON p.player_id = pl.id GROUP BY pl.id ORDER BY pl.name COLLATE NOCASE"
        ).fetchall()
        return [self._with_pct(dict(r)) for r in rows]

    @locked
    def player(self, player_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            f"SELECT pl.id, pl.name, {self._COUNTS} FROM pod_players pl"
            " LEFT JOIN game_result_players p ON p.player_id = pl.id WHERE pl.id = ? GROUP BY pl.id", (player_id,)
        ).fetchone()
        if row is None:
            raise ResultNotFound(player_id)
        out = self._with_pct(dict(row))
        decks = self.conn.execute(
            f"SELECT p.deck_key, {self._COUNTS}, MAX(r.rowid) AS last_played FROM game_result_players p"
            " JOIN game_results r ON r.id = p.result_id WHERE p.player_id = ? AND p.deck_key IS NOT NULL"
            " GROUP BY p.deck_key ORDER BY games DESC, last_played DESC", (player_id,)
        ).fetchall()
        out["decks"] = []
        for d in decks:
            latest = self.conn.execute(
                "SELECT p.deck_name, p.commanders FROM game_result_players p JOIN game_results r ON r.id = p.result_id"
                " WHERE p.player_id = ? AND p.deck_key = ? ORDER BY r.rowid DESC LIMIT 1", (player_id, d["deck_key"])
            ).fetchone()
            entry = self._with_pct(dict(d))
            entry.update(deck_name=latest["deck_name"], commanders=json.loads(latest["commanders"]))
            if entry["games"]:
                out["decks"].append(entry)
        out["recent"] = [
            {**{k: g[k] for k in ("id", "number", "recorded_at", "result_type", "table_name", "turns")},
             **{k: me[k] for k in ("deck_name", "commanders", "outcome")}}
            for g in self.history(limit=20, player_id=player_id)
            for me in g["players"] if me["player_id"] == player_id
        ]
        return out

    @locked
    def export(self) -> dict[str, Any]:
        """Everything, for backups (plain JSON)."""
        return {"format": "fyodor-pod-stats", "version": 1, "exported_at": _now(),
                "players": [dict(r) for r in self.conn.execute("SELECT id, name, created_at FROM pod_players")],
                "results": self.history(limit=1_000_000)}
