"""-- quick undo request (TABLETOP_QOL_MILESTONE #7) -- an undo that asks the table first.

At a LAN table two things make an undo ask instead of happening at once:

1. **The host's undo setting refuses it** (``app/game/undo_rights.py``): the player may ask the table instead.
2. **The action to take back showed hidden information or a random outcome** (under every setting, the default "everyone"
   included): undoing a draw, a look at a library, a reveal, a search, a shuffle, a die roll, a coin flip or a random
   pick would let the table play the moment again knowing what came out, so it is never taken back silently. Actions that
   show nothing new (a cast from your hand, a land, an attack, a life change, a pass that draws nothing) undo as before.

**What an action showed** is decided by the server as it records the action and kept on it (``Base.shown``, a category,
never a card), so saves, the crash journal, redo and replays keep it. :func:`classify` reads it from:

* what the action did, the steps the rules engine compiled into an intent included (:data:`STEP_KINDS`): a draw, a
  search, a look at a library, a reveal, a mill or a card put face down from a library, a shuffle, roll, flip, random
  discard, mulligan or deck reset;
* what it changed: a library card nobody was shown before the action that someone can see after it, whether it left the
  library (drawn into a hand: "draw"; anywhere else: "library") or is shown where it lies (revealed, an open look or search,
  a top card a static ability shows: "look"); and a private choice that searches a library or looks at its top cards
  (scry, surveil) beginning (:data:`DECISION_KINDS`);
* whether it drew on the server's randomness at all (a random pick by the rules engine: "random"), see :class:`Recorder`.

Every input is something the table can see happened (step types, zone changes, reveals, looks, that a search began), never
which cards a private choice offers: a search that finds nothing asks the same as one that finds something, so whether an
undo asks tells nobody what is in a library. Actions recorded before this existed fall back to the first rule (:func:`shown`).

**Who approves** (as for an agreed ending, ``app/api/night.py``): every other seated player still in the game; one
decline ends the request. A LAN seat nobody has taken can't answer, so it isn't asked. The host has no casting vote: their
override stays Snapshots & history > Restore from here. When nobody else could answer there is no one to ask: an undo the
setting refuses stays refused, and an undo of something already seen goes ahead as before.

**Hot-seat tables** (one computer): approval would be one person asking themselves, so undo stays direct there (only the
undo setting applies, as before). The API passes ``others=None`` for them.

A request takes back exactly the action that was last when it was made: any change to the table (a new action, an undo, a
redo, a restore) cancels it, and the requester may withdraw it. Approved, the server performs the undo, attributed to the
requester and logged "with the table's approval". Requests live in memory with the table (like the end-game votes): a
saved or recovered game has none waiting.

**Privacy:** a request names the action by its type, and names its card only for a cast, a land play or an activation
whose card everyone can see now ("Undo cast Sol Ring"); never a hidden card ("Undo draw", not the card drawn). What it
showed is one of the categories, never a card. Who acted is public already (the log, GET /history).
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from app.game import out_of_game, undo_rights
from app.game.actions import Action
from app.game.control import is_controlled
from app.game.errors import ActionError
from app.game.history import History
from app.game.state import GameState
from app.game.visibility import can_see, publicly_visible

if TYPE_CHECKING:
    from app.game.session import GameSession

log = logging.getLogger(__name__)

Shown = Literal["draw", "search", "look", "reveal", "library", "random"]

# What a step showed, by its type (the action itself, or a step the rules engine compiled into an intent or a macro).
STEP_KINDS: dict[str, Shown] = {
    "draw": "draw", "mulligan_take": "draw",
    "search_start": "search", "fetch_card": "search",
    "look_top": "look",
    "reveal": "reveal", "reveal_top": "reveal", "reveal_until": "reveal", "cascade": "reveal",
    "mill": "library", "put_top_face_down": "library",
    "shuffle": "random", "mulligan": "random", "roll": "random", "coin": "random", "discard_random": "random",
    "reset_deck": "random", "restart_game": "random", "load_deck": "random",
}
# These shuffle only when they carry a shuffle (``r``): ending a search with "shuffle", a mulligan's final shuffle.
SHUFFLE_IF_RESOLVED = frozenset({"search_end", "mulligan_keep", "mulligan_bottom"})
# The most telling first, when an action did several things.
ORDER: tuple[Shown, ...] = ("draw", "search", "look", "reveal", "library", "random")
# The table jumping to another recorded moment shows nothing anyone hadn't seen (the cards it replaces are new objects).
NOT_A_CHANGE = frozenset({"restore_state"})
# The rules engine's private choices that look into a library, by their (server-side) step: a search (701.23, asked even when
# nothing matches) and a scry / surveil (701.22, 701.25). Read from what the choice is, never from the cards it offers.
DECISION_KINDS: dict[str | None, Shown] = {"search": "search", "look": "look"}

WHAT: dict[Shown, str] = {
    "draw": "a draw",
    "search": "a library search",
    "look": "a look at cards in a library",
    "reveal": "a reveal",
    "library": "cards that came out of a library",
    "random": "a random result (a shuffle, a roll, a flip or a random pick)",
}

# How a request names an action: the history's type, in words (never a hidden card, see ``label``).
WORDS = {"pass_priority": "pass priority", "cast_spell": "cast", "play_land": "play", "activate_ability": "activate",
         "choose": "answer", "declare_attackers": "declare attackers", "declare_blockers": "declare blockers",
         "life": "life change", "set_life": "life total", "move": "move cards", "set_position": "move cards"}
NAMES_ITS_CARD = frozenset({"cast_spell", "play_land", "activate_ability"})


def reason(kind: Shown) -> str:
    return f"This undo would take back {WHAT[kind]} that players already saw."


# ---------------------------------------------------------------------------- what an action showed


class Recorder:
    """The randomness source for one action: passes every call through, and remembers that the action used it."""

    def __init__(self, rng: Any = None) -> None:
        if rng is None:
            # resolve's own source (a system source): the one object the table's randomness comes from, so a test that pins it
            # (tests/wave47b_kit.py ``pin_random``) pins the rules engine's random picks too
            from app.game import resolve

            rng = resolve._rng
        self._rng = rng
        self.used = False

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        self.used = True
        return getattr(self._rng, name)


def _steps(action: Action) -> Iterator[tuple[str, bool]]:
    """(type, carries resolved data) of the action and of each step compiled into it."""
    yield action.type, getattr(action, "r", None) is not None
    for nested in (getattr(action, "r", None), getattr(action, "opening", None)):
        if isinstance(nested, list):
            for step in nested:
                if isinstance(step, dict):
                    yield str(step.get("type")), step.get("r") is not None


def by_steps(action: Action) -> Shown | None:
    found: set[Shown] = set()
    for kind, resolved in _steps(action):
        if kind in STEP_KINDS:
            found.add(STEP_KINDS[kind])
        elif kind in SHUFFLE_IF_RESOLVED and resolved:
            found.add("random")
    return next((k for k in ORDER if k in found), None)


def _seen_in_libraries(state: GameState) -> set[str]:
    """Library cards someone is shown right now: revealed (the top card by a static ability too), or in an open search or look.
    Never read from a pending choice's options: which cards a search offers is the searcher's alone (it would tell the table
    whether anything matched), so a choice counts by what it is (:data:`DECISION_KINDS`)."""
    out: set[str] = set()
    for view in state.views:
        if view.zone.endswith(":library"):
            out |= set(state.zones.get(view.zone, [])) if view.kind == "search" else set(view.card_ids)
    for key, ids in state.zones.items():
        if not key.endswith(":library") or not ids:
            continue
        out |= {cid for cid in ids if (c := state.cards.get(cid)) is not None and c.revealed_to}
        top = state.cards.get(ids[0])
        if top is not None and any(can_see(state, top, p) for p in state.seat_order):
            out.add(top.id)
    return out


@dataclass(frozen=True)
class Before:
    """The table just before an action: its library cards nobody was shown, and the pending choice."""

    unseen: frozenset[str] = frozenset()
    decision: str | None = None


def before(state: GameState) -> Before:
    try:
        seen = _seen_in_libraries(state)
        unseen = frozenset(cid for key, ids in state.zones.items() if key.endswith(":library") for cid in ids if cid not in seen)
        return Before(unseen, state.rules.decision.id if state.rules is not None and state.rules.decision is not None else None)
    except Exception:  # noqa: BLE001 - a note for undo must never stop an action; it is logged loudly
        log.exception("Could not read the libraries before an action")
        return Before()


def by_change(was: Before, state: GameState) -> Shown | None:
    """After an action: did a library card nobody was shown before come to be seen, or did a search or a look begin?"""
    found: set[Shown] = set()
    decision = state.rules.decision if state.rules is not None else None
    if decision is not None and decision.id != was.decision and (kind := DECISION_KINDS.get((decision.resume or {}).get("step"))):
        found.add(kind)
    seen = _seen_in_libraries(state)
    for cid in was.unseen:
        card = state.cards.get(cid)
        if card is None:  # a new object now (put face down where others see it, 406.3): who may look isn't known here
            found.add("library")
        elif card.zone.endswith(":library"):
            if cid in seen:
                found.add("look")
        elif any(can_see(state, card, p) for p in state.seat_order):
            found.add("draw" if card.zone.endswith(":hand") else "library")
    return next((k for k in ORDER if k in found), None)


def classify(action: Action, was: Before, state: GameState, random_used: bool) -> Shown | None:
    """What a just-applied action showed (``was``: :func:`before` of the table it was applied to)."""
    try:
        if (kind := by_steps(action)) is not None:
            return kind
        if action.type not in NOT_A_CHANGE and (kind := by_change(was, state)) is not None:
            return kind
    except Exception:  # noqa: BLE001 - the action is applied already: recording it must not fail (logged loudly)
        log.exception("Could not tell what %s showed", action.type)
    return "random" if random_used else None


def shown(action: Action | None) -> Shown | None:
    """What a recorded action showed (older saves: what its steps say)."""
    if action is None:
        return None
    return action.shown or by_steps(action)


def label(state: GameState, action: Action) -> str:
    """What "Undo …" takes back: "cast Sol Ring", "draw". The card only when everyone can see it now."""
    words = WORDS.get(action.type, action.type.replace("_", " "))
    card = state.cards.get(str(getattr(action, "card_id", ""))) if action.type in NAMES_ITS_CARD else None
    if card is not None and card.name and publicly_visible(state, card):
        words = f"{words} {card.name}"
    return words


# ---------------------------------------------------------------------------- the request


@dataclass
class UndoRequest:
    by: str
    cursor: int  # the history position it was made at; the action it takes back is the one before
    target: Action
    label: str
    shown: Shown | None
    refused: str | None  # what the undo setting said, when it refused the direct undo
    voters: list[str]
    approved: set[str] = field(default_factory=set)
    id: str = field(default_factory=lambda: secrets.token_hex(4))

    def current(self, history: History) -> bool:
        """Still about the last action (any change to the table ends it)."""
        return history.cursor == self.cursor > 0 and history.actions[self.cursor - 1] is self.target

    def public(self, state: GameState) -> dict[str, Any]:
        names = {pid: p.name for pid, p in state.players.items()}
        return {"id": self.id, "by": self.by, "by_name": names.get(self.by, self.by), "label": self.label,
                "shown": self.shown, "why": reason(self.shown) if self.shown else None,
                "voters": list(self.voters), "approved": sorted(self.approved),
                "waiting": [pid for pid in self.voters if pid not in self.approved]}


def still_in(state: GameState) -> list[str]:
    """Players still in the game: not removed from the table, not conceded or lost (800.4a)."""
    r = state.rules
    return [pid for pid in state.seat_order
            if not state.players[pid].left and (r is None or (pid not in r.conceded and pid not in r.lost))]


def ask(session: GameSession, actor: str | None, *, host: bool, others: list[str] | None) -> str | None:
    """Why an undo by ``actor`` would ask the table now (the undo setting's refusal, or what the action showed), or None: a
    direct undo, nothing to undo, or no one to ask (``others``: who would approve, None at a hot-seat table)."""
    target = undo_rights.entry(session.history, "undo")
    if actor is None or not others or target is None or out_of_game.history_refusal(session.state, actor, host=host) is not None:
        return None  # (-- out of the game (gaps5) -- a player who is out can't ask either: their undo is refused outright)
    if (refused := undo_rights.refusal(session.state, session.history, actor, host=host, op="undo")) is not None:
        return refused
    kind = shown(target)
    return reason(kind) if kind is not None else None


def pending(session: GameSession) -> UndoRequest | None:
    req = session.undo_request
    return req if req is not None and req.current(session.history) else None


def request(session: GameSession, actor: str, *, host: bool, others: list[str] | None) -> UndoRequest:
    """``actor`` asks the table to undo the last action (when a direct undo would refuse or ask)."""
    state, history = session.state, session.history
    if others is None:
        raise ActionError("At a hot-seat table, undo directly: there is no one else to ask.")
    if is_controlled(state, actor):
        raise ActionError("Another player is making your choices right now (you can still concede)")
    if (out := out_of_game.history_refusal(state, actor, host=host)) is not None:
        raise ActionError(out)  # -- out of the game (gaps5) -- as their own undo (GameSession.undo)
    if (waiting := pending(session)) is not None:
        raise ActionError(f"{state.players[waiting.by].name}'s undo request is already waiting for the table.")
    target = undo_rights.entry(history, "undo")
    if target is None:
        raise ActionError("Nothing to undo")
    refused = undo_rights.refusal(state, history, actor, host=host, op="undo")
    kind = shown(target)
    if refused is None and (kind is None or not others):
        raise ActionError("Nothing to ask: you can undo that yourself.")
    if not others:
        raise ActionError(f"{refused} Nobody else in the game could approve a request.")
    req = UndoRequest(by=actor, cursor=history.cursor, target=target, label=label(state, target), shown=kind,
                      refused=refused, voters=list(others))
    session.undo_request = req
    session.notice(f"{state.players[actor].name} asks the table to undo: {req.label}.", actor)
    return req


def answer(session: GameSession, actor: str, op: Literal["approve", "decline", "withdraw"]) -> Action | None:
    """A player answers the waiting request (the requester may withdraw it). Returns the action undone once everyone
    approved."""
    req = pending(session)
    if req is None:
        raise ActionError("No undo request is waiting")
    names = {pid: p.name for pid, p in session.state.players.items()}
    if op == "withdraw":
        if actor != req.by:
            raise ActionError("Only the player who asked can withdraw it")
        session.undo_request = None
        session.notice(f"{names[actor]} withdrew their undo request ({req.label}).", actor)
        return None
    if actor not in req.voters:
        raise ActionError("Only the other players still in the game answer this")
    if op == "decline":
        session.undo_request = None
        session.notice(f"{names[actor]} declined {names[req.by]}'s undo request ({req.label}). The game goes on.", actor)
        return None
    req.approved.add(actor)
    if any(pid not in req.approved for pid in req.voters):
        return None
    session.undo_request = None
    return session.undo(req.by, approved=req.label)


def view_fields(session: GameSession, viewer: str, *, host: bool, others: list[str] | None) -> dict[str, Any]:
    """The waiting request (public: who asks, what, what it showed, who still has to answer), and why this viewer's own
    undo would ask the table now (None: it undoes directly, or can't)."""
    req = pending(session)
    return {"undo_request": req.public(session.state) if req is not None else None,
            "undo_ask": ask(session, viewer if viewer in session.state.players else None, host=host, others=others)}
