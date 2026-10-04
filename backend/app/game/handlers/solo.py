"""Solo testing: spawn any card as a test object, reset a deck, restart the game."""

from __future__ import annotations

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.handlers.zones import draw_cards, rekey_zone
from app.game.ops import log, pname, text
from app.game.state import DEFAULT_RESOURCES, CardInstance, GameState, MergedPart, zone_key


def spawn_card(state: GameState, a: A.SpawnCard) -> None:
    if not state.settings.allow_test_objects:
        raise ActionError("Spawning test cards is off at this table (the host can enable it)")
    if a.r is None or not a.r.ids or not a.resolved_name:
        raise ActionError("That card isn't in the card database")
    pid = ops.player(state, a.player, a.actor)
    key = zone_key(pid, a.zone)
    c = CardInstance(id=a.r.ids[0], card_id=a.card_id, name=a.resolved_name, owner=pid, controller=pid, zone=key,
                     test_object=True, x=a.x if a.x is not None else 40.0, y=a.y if a.y is not None else 40.0)
    state.cards[c.id] = c
    state.zone(key).insert(0, c.id) if a.zone == "library" else state.zone(key).append(c.id)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" spawned a test object: "), ops.card_part(state, c)])


def generated(c: CardInstance | MergedPart) -> bool:
    return c.is_token or c.copy_of is not None or getattr(c, "ability", None) is not None or c.test_object


def library_size_after_reset(state: GameState, pid: str) -> int:
    # (-- merged permanents (wave 18D) -- every card of a merged or melded permanent comes back on its own)
    n = 0
    for c in state.cards.values():
        pile: list[CardInstance | MergedPart] = [*c.merged] if c.merged else [c]
        n += sum(1 for p in pile if p.owner == pid and not generated(p) and p.origin == "library" and not p.commander_key)
    return n


def _reset(state: GameState, pid: str, shuffle: A.ShuffleData | None, *, reset_life: bool, draw: int) -> None:
    for c in [c for c in state.cards.values() if c.merged and c.owner == pid]:  # (wave 18D) the piles break up first
        ops.move_card(state, c, zone_key(pid, "graveyard"))
    for c in list(state.cards.values()):
        if c.id not in state.cards:
            continue
        if c.owner == pid and generated(c):
            ops.delete(state, c)
        elif c.owner == pid:
            dest = zone_key(pid, "command" if c.commander_key else c.origin)
            if c.zone != dest:
                ops.move_card(state, c, dest, position="bottom")
            c.face_down = False
            c.face_down_kind = None
    state.arrows = [ar for ar in state.arrows if ar.owner != pid]
    if shuffle is None:
        raise ActionError("unresolved reset")
    rekey_zone(state, zone_key(pid, "library"), shuffle.perm, shuffle.new_ids)
    p = state.players[pid]
    if reset_life:
        p.life = state.settings.starting_life
        p.life_history = []
        p.resources = {k: 0 for k in DEFAULT_RESOURCES}
        p.commander_damage = {}
        p.commander_tax = {k: 0 for k in p.commander_tax}
        p.commander_casts = {}
        p.mana = {}
        p.mana_units = []  # (wave 18B)
        p.mulligans = 0
    if draw:
        draw_cards(state, pid, draw)


def reset_deck(state: GameState, a: A.ResetDeck) -> None:
    pid = ops.player(state, a.player, a.actor)
    _reset(state, pid, a.r, reset_life=a.reset_life, draw=a.draw)
    log(state, a.actor, a.ts, [pname(state, pid), text(f"'s deck was reset and shuffled{f', drew {a.draw}' if a.draw else ''}")])


def restart_game(state: GameState, a: A.RestartGame) -> None:
    if a.r is None:
        raise ActionError("unresolved restart")
    for pid in state.seat_order:
        _reset(state, pid, a.r.get(pid), reset_life=True, draw=a.draw)
    state.turn.number = 1
    state.turn.phase = "untap"
    state.table.monarch = None
    state.table.initiative = None
    state.table.day_night = None
    state.pregame = None
    state.response = None
    state.auto_pass = {}
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" restarted the game: every deck reset and shuffled")])
