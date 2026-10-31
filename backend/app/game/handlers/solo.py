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


def library_size_after_reset(state: GameState, pid: str, keep: set[str] | frozenset[str] = frozenset()) -> int:
    # (-- merged permanents (wave 18D) -- every card of a merged or melded permanent comes back on its own)
    n = 0
    for c in state.cards.values():
        pile: list[CardInstance | MergedPart] = [*c.merged] if c.merged else [c]
        n += sum(1 for p in pile if p.owner == pid and not generated(p) and p.origin == "library" and not p.commander_key and c.id not in keep)
    return n


def _reset(state: GameState, pid: str, shuffle: A.ShuffleData | None, *, reset_life: bool, draw: int, keep: set[str] | frozenset[str] = frozenset()) -> None:
    for c in [c for c in state.cards.values() if c.merged and c.owner == pid]:  # (wave 18D) the piles break up first
        ops.move_card(state, c, zone_key(pid, "graveyard"))
    for c in list(state.cards.values()):
        if c.id not in state.cards or c.id in keep:
            continue  # (wave 110A: 727.5 a card the restart leaves in exile)
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
        p.city_blessing = False  # (wave 110A) 727: nothing of the old game carries over
    if draw:
        draw_cards(state, pid, draw)


def reset_deck(state: GameState, a: A.ResetDeck) -> None:
    pid = ops.player(state, a.player, a.actor)
    _reset(state, pid, a.r, reset_life=a.reset_life, draw=a.draw)
    log(state, a.actor, a.ts, [pname(state, pid), text(f"'s deck was reset and shuffled{f', drew {a.draw}' if a.draw else ''}")])


def restart_game(state: GameState, a: A.RestartGame) -> None:
    if a.r is None:
        raise ActionError("unresolved restart")
    rules_restart = a.first is not None  # -- wave 110A -- 727: a restart by Karn Liberated, run by the rules engine
    from app.game.control import _live

    players = [pid for pid in state.seat_order if not rules_restart or _live(state, pid)]  # 727.1: the players still in the game
    policy = state.settings.mulligan if rules_restart else None
    keep = set(a.keep)
    for pid in players:
        _reset(state, pid, a.r.get(pid), reset_life=True, draw=0 if policy is not None else a.draw, keep=keep)
    state.turn.number = 1
    state.turn.phase = "untap"
    state.turn.starting_life = {pid: p.life for pid, p in state.players.items()}
    state.turn.starting_hand = None  # (wave 110G) the hands are about to be redrawn
    state.table.monarch = None
    state.table.initiative = None
    state.table.day_night = None
    state.pregame = None
    state.response = None
    state.auto_pass = {}
    if rules_restart:
        from app.game.handlers import mulligan
        from app.game.rules_state import RulesState, start_rules

        assert a.first is not None
        state.turn.active_player = a.first  # 727.1a
        state.views = []
        old = state.rules
        fresh = start_rules(state)  # 727: no effect, emblem, delayed trigger or history of the old game remains
        if old is not None:
            for name in ("conceded", "lost", "prefs", "card_modes", "paused", "engine_version"):
                setattr(fresh, name, getattr(old, name))
            for name in RulesState.model_fields:
                setattr(old, name, getattr(fresh, name))
            state.rules = old  # (in place: the rules engine's callers still hold this object)
        if state.rules is not None and keep:
            state.rules.restart110a = {"controller": a.first, "cards": [c for c in a.keep if c in state.cards]}
        if policy is not None:
            mulligan.begin(state, a.ts)  # 103.4: the new game's opening hands and mulligans; the kept cards come after (opening_hand.finish)
            if state.rules is not None:
                state.rules.priority = None
        log(state, a.actor, a.ts, [pname(state, a.first), text(" restarted the game (Karn Liberated, 727): a new game begins")])
        return
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" restarted the game: every deck reset and shuffled")])


def load_deck(state: GameState, a: A.LoadDeck) -> None:
    """A new deck in a seat, mid-game (the scripted tables' importer): the owner's cards, tokens and copies leave the
    table, the new deck's cards arrive in their zones (commander in the command zone, the rest shuffled into the
    library), life goes back to the start and, unless told otherwise, seven are drawn."""
    from app.game.factory import SECTION_ZONES
    pid = ops.player(state, a.player, a.actor)
    if a.r is None:
        raise ActionError("unresolved deck")
    if not any(c.section in ("main", "commander") for c in a.cards):
        raise ActionError("That deck has no cards")
    for c in [c for c in state.cards.values() if c.merged and c.owner == pid]:  # merged piles break up first
        ops.move_card(state, c, zone_key(pid, "graveyard"))
    gone: set[str] = set()
    old_keys = {c.commander_key for c in state.cards.values() if c.owner == pid and c.commander_key}
    for c in [c for c in state.cards.values() if c.owner == pid]:
        if c.id in state.cards:
            gone.add(c.id)
            ops.delete(state, c)
    state.arrows = [ar for ar in state.arrows if ar.owner != pid and ar.source not in gone and not gone.intersection(ar.targets)]
    state.views = [v for v in state.views if v.viewer != pid]
    ids = iter(a.r.ids)
    p = state.players[pid]
    p.commander_tax = {}
    p.commander_casts = {}
    for other in state.players.values():
        for key in old_keys:
            other.commander_damage.pop(key, None)
    n = 0
    library = zone_key(pid, "library")
    for entry in a.cards:
        zone = SECTION_ZONES.get(entry.section)
        if zone is None:
            continue
        for _ in range(entry.quantity):
            cid = next(ids, None)
            if cid is None or cid in state.cards:
                raise ActionError("unresolved deck")
            card = CardInstance(id=cid, card_id=entry.printing_id, name=entry.name, owner=pid, controller=pid,
                                zone=zone_key(pid, zone), origin=zone)  # type: ignore[arg-type]
            if entry.section == "commander":
                n += 1
                card.commander_key = f"cmd-{pid}-{cid[:6]}-{n}"
                card.protected = True
                p.commander_tax[card.commander_key] = 0
            state.cards[cid] = card
            state.zone(card.zone).append(cid)
    lib = state.zone(library)
    if sorted(a.r.perm) != list(range(len(lib))):
        raise ActionError("unresolved deck")
    lib[:] = [lib[i] for i in a.r.perm]  # shuffled (the ids are new: nothing links them to the old deck)
    p.deck_name = a.deck_name
    p.deck_id = a.deck_id
    p.life = state.settings.starting_life
    p.life_history = []
    p.resources = {k: 0 for k in DEFAULT_RESOURCES}
    p.commander_damage = {}
    p.mana = {}
    p.mana_units = []
    p.mulligans = 0
    if a.draw:
        draw_cards(state, pid, a.draw)
    total = sum(c.quantity for c in a.cards if c.section in ("main", "commander"))
    log(state, a.actor, a.ts, [pname(state, pid), text(f" placed a new deck at the table: {a.deck_name} ({total} cards), shuffled"
                                                      f"{f', drew {a.draw}' if a.draw else ''}")])

