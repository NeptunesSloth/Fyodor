"""Game night: several games with the same pod at one room (docs/GAME_NIGHT_FLOW.md).

The room outlives each game. ``Night`` holds what carries over (who brought which deck, the last
turn order and result) and the post-game decisions (an agreed ending, the rematch vote). Nothing
match-local carries into the next game: a rematch builds a brand-new game from the same decks.

Turn order follows the pod rule: game 1 and every game after a draw open with server-side d20
rolls (ties reroll among the tied players only); otherwise the previous winner goes last and the
others keep their relative order. Clients never roll or decide anything.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from app.game.factory import PlayerSetup
from app.game.state import GameState
from app.multiplayer.lobby import LobbySeatInfo, SubmittedDeck, TurnOrder

if TYPE_CHECKING:
    from app.multiplayer.hub import Room

log = logging.getLogger(__name__)

OrderSource = Literal["d20", "winner_last", "host"]
Choice = Literal["rematch", "lobby"]
ResultType = Literal["single", "multiple", "draw", "no_result"]

# -- final board -- once a result is recorded the table is the final board (3D_DIRECTION.md §7a "View final board"): anyone
# may look at it (either renderer, the camera, card details, the log), nothing may change it. Table talk and closing a private
# look at cards ("end_view": it only hides them again) change no card, zone or counter, so they stay open; everything else
# waits for the rematch or the lobby.
FINAL_BOARD = "The game is over: the final board can be looked at but not changed. Rematch or return to the lobby to play again."
POSTGAME_ACTIONS = frozenset({"chat", "end_view"})


def d20() -> int:
    return secrets.randbelow(20) + 1


def roll_order(keys: list[str], roll: Callable[[], int] = d20) -> tuple[list[str], list[dict[str, int]]]:
    """Order ``keys`` by d20, highest first. Ties reroll among the tied players only, as often as needed.

    Returns the order and every round of rolls (round 0 is everyone; later rounds are tie-breaks).
    """
    rounds: list[dict[str, int]] = []

    def settle(group: list[str]) -> list[str]:
        if len(group) <= 1:
            return list(group)
        rolls = {k: roll() for k in group}
        rounds.append(rolls)
        out: list[str] = []
        for value in sorted(set(rolls.values()), reverse=True):
            out += settle([k for k in group if rolls[k] == value])
        return out

    return settle(list(keys)), rounds


def winner_last(order: list[str], winner: str) -> list[str]:
    """The previous winner goes last; everyone else keeps their relative order."""
    if winner not in order:
        return list(order)
    return [k for k in order if k != winner] + [winner]


@dataclass
class Proposal:
    """A player's proposal to end the game now with a given result; every remaining player must agree.

    -- rules result -- or the rules engine's own result, opened by the server when the engine ends the game (104.1):
    ``rules`` says why (public: the losses and draw reasons are in every view already), ``voters`` are the players who were
    still in the game when it ended, and each confirms it with one click (at a hot-seat table one click settles it)."""

    by: str
    result_type: ResultType
    winners: list[str]
    agreed: set[str] = field(default_factory=set)
    rules: str | None = None
    voters: list[str] = field(default_factory=list)

    def public(self, names: Callable[[str], str]) -> dict[str, Any]:
        return {"by": self.by, "by_name": "The rules" if self.rules is not None else names(self.by),
                "result_type": self.result_type, "winners": list(self.winners),
                "winner_names": [names(w) for w in self.winners], "agreed": sorted(self.agreed),
                "rules": self.rules, "voters": list(self.voters)}


@dataclass
class Night:
    number: int = 1  # the game number within this pod session
    order_source: OrderSource = "host"
    rolls: list[dict[str, int]] = field(default_factory=list)  # d20 rounds for this game, by game seat
    previous_winner: str | None = None  # game seat of last game's winner (who now goes last)
    # What each seat brought to this game (game seat -> setup), for a same-decks rematch.
    setups: dict[str, PlayerSetup] = field(default_factory=dict)
    # Lobby seat info (deck, colour, name) per game seat, so returning to the lobby keeps each deck selected.
    infos: dict[str, LobbySeatInfo] = field(default_factory=dict)
    proposal: Proposal | None = None
    # After a recorded result: the outcome and each seat's choice.
    result: dict[str, Any] | None = None
    votes: dict[str, Choice] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)  # one entry per finished game
    # Seat token (or, at a hot-seat table, game seat) of the last game's single winner; never sent to clients.
    last_winner_key: str | None = None
    # Monotonic times of recent nudges / reactions (rate limits; in memory only, never sent or saved).
    signals: dict[str, float] = field(default_factory=dict)
    # -- rules result -- the engine's ending ("win:p2", "draw:<reason>") the last change of the table showed, None while the
    # game goes on; in memory only, so a restored table asks again
    rules_end: str | None = None
    # (spectator activities) the host's table-wide switch for reactions (default on; each player can also mute them)
    reactions: bool = True
    # (spectator activities) next-game decks queued by players who are out and by spectators, by seat or spectator token.
    # In memory only, never sent; applied when the pod returns to the lobby (a same-decks rematch ignores them).
    queued: dict[str, SubmittedDeck] = field(default_factory=dict)

    def final_board(self, action_type: str | None = None) -> str | None:
        """-- final board -- why the table refuses a change now (``action_type``: the action asked for; None: an undo, a
        redo, a restore or any other change), or None while the game goes on."""
        if self.result is None or action_type in POSTGAME_ACTIONS:
            return None
        return FINAL_BOARD

    def result_key(self, room_id: str) -> str:
        """The pod-stats game id of the current game (game 1 keeps the room id; later games add #n)."""
        return room_id if self.number == 1 else f"{room_id}#{self.number}"

    @staticmethod
    def plan(seats: list[str], winner: str | None, roll: Callable[[], int] = d20) -> tuple[list[str], OrderSource, list[dict[str, int]]]:
        """Turn order for the next game over ``seats``: the previous single winner goes last, else d20."""
        if winner is not None and winner in seats:
            return winner_last(seats, winner), "winner_last", []
        order, rounds = roll_order(seats, roll)
        return order, "d20", rounds

    @staticmethod
    def preview(seats: list[str], winner: str | None, mode: TurnOrder) -> dict[str, Any]:
        """-- seating -- what the next game's order will be, for the lobby (public: seats, and last game's winner, whose win
        everyone saw). ``seats``: the claimed seats as the host arranged them. Under the pod rule a d20 roll (game 1, after a
        draw) can't be known before the start, so ``order`` is then just the seating."""
        if mode == "pod":
            if winner is not None and winner in seats:
                return {"source": "winner_last", "order": winner_last(seats, winner), "previous_winner": winner}
            return {"source": "d20", "order": list(seats), "previous_winner": None}
        return {"source": mode, "order": list(seats), "previous_winner": None}

    def remap(self, mapping: dict[str, str]) -> None:
        """Seats were renumbered for a new game (old seat -> new seat)."""
        self.setups = {mapping[k]: v for k, v in self.setups.items() if k in mapping}
        self.infos = {mapping[k]: v for k, v in self.infos.items() if k in mapping}
        self.rolls = [{mapping[k]: v for k, v in r.items() if k in mapping} for r in self.rolls]
        self.previous_winner = mapping.get(self.previous_winner or "")

    def public(self, names: Callable[[str], str]) -> dict[str, Any]:
        """Everything here is public: rolls, order, proposals, the result and the votes."""
        return {
            "number": self.number,
            "order_source": self.order_source,
            "rolls": [dict(r) for r in self.rolls],
            "previous_winner": self.previous_winner,
            "proposal": self.proposal.public(names) if self.proposal else None,
            "result": self.result,
            "votes": dict(self.votes),
            "history": [dict(h) for h in self.history],
            "reactions": self.reactions,
        }

    def meta(self) -> dict[str, Any]:
        """Crash-recovery record (setups and lobby infos are rebuilt by the host if lost)."""
        return {"number": self.number, "order_source": self.order_source, "rolls": self.rolls,
                "previous_winner": self.previous_winner, "result": self.result, "votes": dict(self.votes),
                "history": self.history, "last_winner_key": self.last_winner_key, "reactions": self.reactions}

    @classmethod
    def from_meta(cls, meta: dict[str, Any] | None) -> Night:
        night = cls()
        if not meta:
            return night
        night.number = int(meta.get("number") or 1)
        night.order_source = meta.get("order_source") or "host"
        night.rolls = list(meta.get("rolls") or [])
        night.previous_winner = meta.get("previous_winner")
        night.result = meta.get("result")
        night.votes = dict(meta.get("votes") or {})
        night.history = list(meta.get("history") or [])
        night.last_winner_key = meta.get("last_winner_key")
        night.reactions = bool(meta.get("reactions", True))
        return night


# --------------------------------------------------------------------------- rules result


def still_in(state: GameState) -> list[str]:
    """Players still in the game: not removed from the table, not conceded or lost (800.4a)."""
    r = state.rules
    return [pid for pid in state.seat_order
            if not state.players[pid].left and (r is None or (pid not in r.conceded and pid not in r.lost))]


def rules_ending(state: GameState) -> tuple[str, ResultType, list[str]] | None:
    """The rules engine's verdict once it has ended the game (104.1): a winner (104.2) or a draw (104.4)."""
    r = state.rules
    if r is None:
        return None
    if r.winner is not None:
        return f"win:{r.winner}", "single", [r.winner]
    if r.draw_reason is not None:
        from app.rules.dummy_ending import dummy_winners

        if dummies := dummy_winners(state):  # -- target dummy -- only dummies were left: they win (app/rules/dummy_ending.py)
            return f"win:{','.join(dummies)}", "multiple" if len(dummies) > 1 else "single", dummies
        return f"draw:{r.draw_reason}", "draw", []
    return None


def _finalists(room: Room) -> list[str]:
    """The players who were in the game just before the action that ended it, read back from the history (so a table loaded
    from a save or restored after a crash knows them too)."""
    session = room.session
    state = session.state
    history = session.history
    if history.cursor > 0:
        try:
            before = still_in(history.state_at(history.cursor - 1))
            return [pid for pid in before if pid in state.players and not state.players[pid].left]
        except Exception:  # noqa: BLE001 - who confirms is a courtesy; a history that can't replay falls back below
            log.exception("Could not read the table before the game ended")
    return still_in(state) or [pid for pid in state.seat_order if not state.players[pid].left]


def follow_rules(room: Room) -> None:
    """-- rules result -- after every change of a started table (GAME_NIGHT_FLOW.md §4-5): when the rules engine has just
    ended the game, open the end-game proposal with its result, so the spotlight and the rematch vote follow once the players
    confirm it; when an undo (or a restored snapshot) takes the ending back, withdraw it. Nothing is recorded here, and a
    declined rules result stays declined until the ending changes."""
    if room.game is None or room.practice is not None:  # (elimination hub) a practice table never has a pod result
        return
    session = room.game
    state = session.state
    night = room.night
    ending = rules_ending(state)
    key = ending[0] if ending else None
    if key == night.rules_end:
        return
    night.rules_end = key
    current = night.proposal
    if current is not None and current.rules is not None:
        night.proposal = None
        if ending is None:
            session.notice("The game-ending action was taken back, so the rules result is withdrawn. The game goes on.")
    if ending is None or night.result is not None or room.result_id is not None or len(state.seat_order) < 2:
        return
    if any(p.dummy or p.bot is not None for p in state.players.values()):
        return  # -- target dummy -- (and -- test opponent --) a test table: the rules' ending shows at the table (Reset dummy goes on), no pod result to record
    _, result_type, winners = ending
    r = state.rules
    assert r is not None
    finalists = _finalists(room)
    # whoever conceded chose to leave: they don't confirm (the others do, the loser of the deciding action included)
    voters = [pid for pid in finalists if pid not in r.conceded] or still_in(state) or finalists
    if result_type == "draw":
        reason = r.draw_reason or "The game is a draw"
        what = "a draw"
    else:
        why = [f"{room.seat_name(pid)} conceded" if pid in r.conceded else f"{room.seat_name(pid)} lost ({r.lost[pid]})"
               for pid in finalists if pid in r.conceded or pid in r.lost]
        reason = "; ".join(why) or f"{room.seat_name(winners[0])} is the last player in the game"
        what = f"{room.seat_name(winners[0])} wins"
    night.proposal = Proposal(by="", result_type=result_type, winners=list(winners), rules=reason, voters=voters)
    session.notice(f"The rules ended the game: {what}. {reason[:1].upper()}{reason[1:]}. Confirm the result to record it.")
