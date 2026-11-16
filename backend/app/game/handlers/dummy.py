"""-- target dummy -- Sandbox's practice opponent (docs/MACROS_AND_SOLO.md, "Target dummy"): a seat with no deck, standard life,
poison and commander damage, so "each opponent", targeted damage and drain effects have someone to hit.

* It never takes a turn (``next_turn`` and the rules engine's turn skips pass over it), so it never draws from its empty library.
  A draw an effect makes it take doesn't lose it the game either (``app.rules.sba``): it is there to test damage.
* With rules automation on, the server answers its priority and decisions at once, as recorded actions (``app.game.dummy``).
* It loses as anyone does (0 life, 10 poison, 21 commander damage); **Reset dummy** brings it back.
"""

from __future__ import annotations

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


def dummy_of(state: GameState) -> str | None:
    """The table's target dummy (one at most), or None."""
    return next((pid for pid in state.seat_order if state.players[pid].dummy), None)


def add_dummy(state: GameState, a: A.AddDummy) -> None:
    if not state.settings.allow_test_objects:
        raise ActionError("The target dummy is a solo tool: test cards are off at this table (the host can enable them)")
    if dummy_of(state) is not None:
        raise ActionError("This table already has a target dummy")
    if len(state.seat_order) >= MAX_SEATS:
        raise ActionError(f"The table is full ({MAX_SEATS} seats)")
    n = len(state.players) + 1  # (a removed player keeps their id: never reused)
    while f"p{n}" in state.players:
        n += 1
    pid = f"p{n}"
    state.players[pid] = PlayerState(id=pid, name=NAME, color=COLOR, life=state.settings.starting_life, dummy=True)
    state.seat_order.append(pid)
    for zone in PLAYER_ZONES:
        state.zones.setdefault(zone_key(pid, zone), [])
    state.collections.setdefault(pid, [])
    if state.turn.starting_life is not None:
        state.turn.starting_life[pid] = state.settings.starting_life
    if state.turn.starting_hand is not None:
        state.turn.starting_hand[pid] = 0
    if state.pregame is not None and not state.pregame.finished:
        state.pregame.seats[pid] = PregameSeat(status="kept", kept=0)  # nothing to mulligan: the others' keeps start the game
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" added a target dummy: "), pname(state, pid)])


def reset_dummy(state: GameState, a: A.ResetDummy) -> None:
    pid = dummy_of(state)
    if pid is None or state.players[pid].left:
        raise ActionError("There is no target dummy at this table")
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
    p.life = state.settings.starting_life
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
