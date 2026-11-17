"""-- target dummy -- Sandbox's practice opponent (docs/MACROS_AND_SOLO.md, "Target dummy"): a seat with no deck, standard life,
poison and commander damage, so "each opponent", targeted damage and drain effects have someone to hit.

* It never takes a turn (``next_turn`` and the rules engine's turn skips pass over it), so it never draws from its empty library.
  A draw an effect makes it take doesn't lose it the game either (``app.rules.sba``): it is there to test damage.
* With rules automation on, the server answers its priority and decisions at once, as recorded actions (``app.game.dummy``).
  How it blocks is the host's setting (``PlayerState.dummy_blocks``: Add a target dummy, then Solo tools → Dummy blocks).
* It loses as anyone does (0 life, 10 poison, 21 commander damage); **Reset dummy** brings it back.
* A table may seat up to ``MAX_DUMMIES`` of them (the Sandbox start: each with its own name, life and blocks); Reset dummy and
  Dummy blocks name the one they mean (``player``; none: the first, as older histories recorded them).
"""

from __future__ import annotations

from typing import Any

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.ops import log, pname, text
from app.game.state import (
    DEFAULT_RESOURCES,
    PLAYER_ZONES,
    STACK,
    GameState,
    PlayerState,
    PregameSeat,
    split_zone,
    zone_key,
)

NAME = "Target Dummy"
COLOR = "#8a8f98"  # unpainted wood-and-steel grey: no seat colour of its own (its name and the dummy icon say what it is)
MAX_SEATS = 6
MAX_DUMMIES = 3
# how it blocks with automation on (app/game/dummy.py), as the log says it
BLOCKS = {"never": "never blocks", "chump": "chump-blocks the biggest attacker", "all": "blocks with everything it can"}


def dummy_of(state: GameState) -> str | None:
    """The table's first target dummy, or None."""
    return next((pid for pid in state.seat_order if state.players[pid].dummy), None)


def dummies_of(state: GameState) -> list[str]:
    """The table's target dummies, in seat order."""
    return [pid for pid in state.seat_order if state.players[pid].dummy]


def _the_dummy(state: GameState, player: str | None) -> str:
    """The dummy an action means (``player``; none: the first), still at the table."""
    pid = player if player is not None else dummy_of(state)
    if pid is None or pid not in state.players or not state.players[pid].dummy or state.players[pid].left:
        raise ActionError("There is no such target dummy at this table" if player else "There is no target dummy at this table")
    return pid


def test_over(state: GameState, pid: str) -> bool:
    """-- test-table ending -- whether the test is over for ``pid``: the rules ended the game (a winner or a draw), or ``pid`` lost or
    conceded (the dummies may still stand: they never take a turn, so nothing more happens)."""
    r = state.rules
    return r is not None and (r.winner is not None or r.draw_reason is not None or pid in r.lost or pid in r.conceded)


MAX_TAKE_BACK = 200  # players' actions "Take it back" looks back through for where the test ended


def before_the_end(state: GameState, history: Any, pid: str) -> int | None:
    """-- test-table ending -- the history position just before the action that ended the test for ``pid`` (the table's ``state`` now,
    its ``history``): a player's action, the dummies' answers to it going back with it (only the positions before a player's action
    are looked at). None when the test isn't over, or it ended more than MAX_TAKE_BACK player actions back."""
    if not test_over(state, pid):
        return None
    looked = 0
    for position in range(history.cursor - 1, -1, -1):
        if _is_dummy(state, history.actions[position].actor):
            continue
        if not test_over(history.state_at(position), pid):
            return position
        looked += 1
        if looked >= MAX_TAKE_BACK:
            break
    return None


def _is_dummy(state: GameState, pid: str | None) -> bool:
    p = state.players.get(pid) if pid else None
    return p is not None and p.dummy


def add_dummy(state: GameState, a: A.AddDummy) -> None:
    if not state.settings.allow_test_objects:
        raise ActionError("The target dummy is a solo tool: test cards are off at this table (the host can enable them)")
    seated = dummies_of(state)
    if len(seated) >= MAX_DUMMIES:
        raise ActionError(f"This table already has {MAX_DUMMIES} target dummies")
    if len(state.seat_order) >= MAX_SEATS:
        raise ActionError(f"The table is full ({MAX_SEATS} seats)")
    n = len(state.players) + 1  # (a removed player keeps their id: never reused)
    while f"p{n}" in state.players:
        n += 1
    pid = f"p{n}"
    name = (a.name or "").strip() or (NAME if not seated else f"{NAME} {len(seated) + 1}")
    life = a.life if a.life is not None else state.settings.starting_life
    state.players[pid] = PlayerState(id=pid, name=name, color=COLOR, life=life, dummy=True, dummy_blocks=a.blocks,
                                     dummy_life=a.life)
    state.seat_order.append(pid)
    for zone in PLAYER_ZONES:
        state.zones.setdefault(zone_key(pid, zone), [])
    state.collections.setdefault(pid, [])
    if state.turn.starting_life is not None:
        state.turn.starting_life[pid] = life
    if state.turn.starting_hand is not None:
        state.turn.starting_hand[pid] = 0
    if state.pregame is not None and not state.pregame.finished:
        state.pregame.seats[pid] = PregameSeat(status="kept", kept=0)  # nothing to mulligan: the others' keeps start the game
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" added a target dummy: "), pname(state, pid),
                               *([text(f" ({BLOCKS[a.blocks]})")] if a.blocks != "never" else [])])


def set_dummy(state: GameState, a: A.SetDummy) -> None:
    pid = _the_dummy(state, a.player)
    p = state.players[pid]
    if p.dummy_blocks == a.blocks:
        raise ActionError(f"{p.name} already {BLOCKS[a.blocks]}")
    p.dummy_blocks = a.blocks
    log(state, a.actor, a.ts, [pname(state, pid), text(f" {BLOCKS[a.blocks]} from now on (with automation on)")])


def reset_dummy(state: GameState, a: A.ResetDummy) -> None:
    pid = _the_dummy(state, a.player)
    for c in [c for c in state.cards.values() if c.owner == pid]:  # its test objects and tokens (it has no deck)
        if c.id in state.cards:
            ops.delete(state, c)
    for c in list(state.cards.values()):  # a card it was given or that sits on its side goes back to its owner
        holder, zone = split_zone(c.zone)
        if c.zone == STACK or c.ability is not None or (holder != pid and c.controller != pid):
            continue
        if zone == "battlefield":
            ops.lose_attack_target(state, c)
            ops.remove_from_zone(state, c)
            ops.insert(state, c, zone_key(c.owner, "battlefield"))
            c.controller = c.owner
            c.attacking = None
            c.attacking_without_target = None
            c.unblock()
        else:
            ops.move_card(state, c, zone_key(c.owner, zone))
    state.arrows = [ar for ar in state.arrows if ar.owner != pid]
    p = state.players[pid]
    p.life = p.dummy_life if p.dummy_life is not None else state.settings.starting_life
    p.life_history = []
    p.resources = {k: 0 for k in DEFAULT_RESOURCES}
    p.commander_damage = {}
    p.mana = {}
    p.mana_units = []
    p.city_blessing = False
    back = _back_in_the_game(state, pid)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" reset "), pname(state, pid),
                               text(" (back in the game)" if back else "")])


def _back_in_the_game(state: GameState, pid: str) -> bool:
    """A dummy that lost (or a game the rules ended with it) comes back: out of the losers, and the game the rules ended goes on
    when more than one player is in it again. Returns whether it had been out."""
    r = state.rules
    if r is None or (pid not in r.lost and pid not in r.conceded):
        return False
    r.lost.pop(pid, None)
    r.conceded = [p for p in r.conceded if p != pid]
    r.drew_from_empty = [p for p in r.drew_from_empty if p != pid]
    from app.rules.plan import live_players  # rules → game; imported late to stay acyclic

    live = live_players(state)
    if len(live) > 1:
        r.winner = None
        r.draw_reason = None
        if r.priority is None or r.priority not in live:
            r.priority = state.turn.active_player if state.turn.active_player in live else live[0]
    return True
