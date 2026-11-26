"""-- planechase more (wave E1) -- the face-up plane's static abilities (and a few planeswalk / encounter lines) that no native wording
reads, each in its exact Oracle wording, with a small dedicated rule where the engine has none (CR 311.4, 312.4, 113.6p: its abilities
work face up in the command zone; "you" is the planar controller, 311.5). every face-up plane is an object (901.11c: ``_face_defs`` reads each); the collectors below are
called from the engine's own (one line each, marked ``wave E1``).

Statics (``STATIC_KINDS``, added to ``planar.STATIC_KINDS``):

* Lake Silencio: "Still Point in Time — All spells have split second." — a flavor word (207.2c) and a spell grant (spell_grants, 702.61a)
  to every spell, whoever controls it (``all``); while it is face up (ruling 2023-10-13: a planeswalk away ends it).
* Naya: "You may play any number of lands on each of your turns." (305.2: no limit for the planar controller; ``extra_lands``; ruling
  2009-10-01: lands played under it still count after a planeswalk away).
* Naktamun: "Each creature card in your graveyard has embalm. Its embalm cost is equal to its mana cost." — zone_grants' "equal to its
  mana cost" grant, for embalm (702.128a, activated from the graveyard).
* Prahv: "If you cast a spell this turn, you can't attack with creatures." / "If you attacked with creatures this turn, you can't cast
  spells." (``attack_problem`` / ``cast_problem``; ruling 2012-06-01: only declared attackers count, 508.1).
* Skybreen: "Spells that share a card type with the top card of a library can't be cast." (601.3; ruling 2009-10-01: every library's
  top card, any spell, not lands or abilities). The card being cast is not compared with itself (it is the spell).
* Horizon Boughs: "All permanents untap during each player's untap step." — in each untap step every other player's permanents untap
  too (502.3; as Seedborn Muse's: "doesn't untap during its controller's untap step" doesn't apply then; 122.1d stun counters do).
* Edge of Malacol: "If a creature you control would untap during your untap step, put two +1/+1 counters on it instead." (614.1a; rulings
  2012-06-01: only the untap step's untapping is replaced). The held creatures are recorded as the turn begins (``untap_instead``) and get
  their counters in the untap step (``untap_step``). A creature with a stun counter keeps the stun (122.1d) — the engine applies the stun
  first (616.1 would let its controller choose the order); one its controller chose not to untap doesn't "would untap".
* Sea of Sand: "Players reveal each card they draw." (701.20: each draw is noted with the card, ``on_events``) and "Whenever a player draws a
  land / nonland card, …" — the native draw trigger with the drawn card's kind (``obj``: triggers._cond_matches reads the card drawn, which
  the static made public; the trigger event itself never carries it).
* The Doctor's Tomb: "If a creature would die, instead exile it and that creature's controller loses 2 life." — the native "exile it
  instead" (614.1a) with a rider: the life loss is part of the replacing event (614.6; replacements ``loses_e1``).
* TARDIS Bay: "The first spell you cast during each of your turns with mana value 2 or greater has cascade." — the native cascade grant
  (cast_limits.granted_instances) for the first spell of that kind this turn (601.2i: earlier casts count, whenever the plane arrived), only
  during the planar controller's turn (TARDIS rulings 2023-10-13: mana value is the mana cost's, 202.3).
* Singing Towers of Darillium: "Each nonland card in your hand without foretell has foretell. …" — Dream Devourer's static
  (dynamic_zone_keyword_costs56), read on the plane; a card foretold this way keeps the foretell cost it was given after a planeswalk away
  (ruling 2023-10-13).

Triggers:

* We Hope You Like Squirrels: one ability with two trigger events (603.2: ``multi:event+step:upkeep:each``); "that player" is the caster
  or the player whose upkeep it is.
* Amy's Home: "you may exile a nonland card from your hand with a number of time counters on it equal to its mana value. If it doesn't
  have suspend, it gains suspend." — the native optional exile (its card bound, pay_objects) and suspend_grants' ``suspend_found`` with
  the card's own mana value (702.62b: suspended once it has a time counter; a mana value 0 card has suspend and no counter).
* Enigma Ridges: "each player who controls fewer lands than the player who controls the most lands searches … for a number of basic land
  cards less than or equal to the difference …" — ``enigma``: counted as it resolves, each such player in turn order runs the native
  "search your library for up to N basic land cards, reveal them, put them into your hand, then shuffle" as themselves.
* Unyaro: "if you planeswalked to Unyaro this turn" (603.4: an intervening if, ``walked_here``: the planar controller's walk to this plane
  this turn, recorded by ``on_walks``) and "They phase out until a player planeswalks." (702.26; ruling 2023-04-14: they don't phase in in
  the untap step) — a phasing packet (``PhaseLifetime.until_walk_e1``) released by the next planeswalk (``on_walks``, also one made by hand).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

Def = dict[str, Any]

ANY_LANDS = "any_lands_e1"
PRAHV_ATTACK = "prahv_attack_e1"
PRAHV_CAST = "prahv_cast_e1"
TOP_TYPES = "top_type_cast_e1"
UNTAP_ALL = "untap_all_steps_e1"
UNTAP_COUNTERS = "untap_counters_e1"
REVEAL_DRAWS = "reveal_draws_e1"
STATIC_KINDS = frozenset({ANY_LANDS, PRAHV_ATTACK, PRAHV_CAST, TOP_TYPES, UNTAP_ALL, UNTAP_COUNTERS, REVEAL_DRAWS, "spell_grant", "exile_instead",
                          "spell_keyword", "dynamic_zone_keyword56"})
CARD_TYPES = frozenset({"Artifact", "Battle", "Creature", "Enchantment", "Instant", "Kindred", "Land", "Planeswalker", "Sorcery", "Tribal"})

_PLAIN: dict[str, str] = {
    "You may play any number of lands on each of your turns.": ANY_LANDS,  # Naya
    "If you cast a spell this turn, you can't attack with creatures.": PRAHV_ATTACK,  # Prahv
    "If you attacked with creatures this turn, you can't cast spells.": PRAHV_CAST,  # Prahv
    "Spells that share a card type with the top card of a library can't be cast.": TOP_TYPES,  # Skybreen
    "All permanents untap during each player's untap step.": UNTAP_ALL,  # Horizon Boughs
    "If a creature you control would untap during your untap step, put two +1/+1 counters on it instead.": UNTAP_COUNTERS,  # Edge of Malacol
    "Players reveal each card they draw.": REVEAL_DRAWS,  # Sea of Sand
}
_SQUIRRELS = "At the beginning of each player's upkeep and whenever a player casts a spell, that player creates a 1/1 green Squirrel creature token."
_SEA = {"Whenever a player draws a land card, that player gains 3 life.": ("Whenever a player draws a card, that player gains 3 life.", "land card"),
        "Whenever a player draws a nonland card, that player loses 3 life.": ("Whenever a player draws a card, that player loses 3 life.", "nonland card")}
_AMY = ("When you planeswalk to Amy's Home and at the beginning of your upkeep, you may exile a nonland card from your hand with a number of "
        "time counters on it equal to its mana value. If it doesn't have suspend, it gains suspend.")
_ENIGMA = ("When you planeswalk to Enigma Ridges, each player who controls fewer lands than the player who controls the most lands searches their "
           "library for a number of basic land cards less than or equal to the difference, reveals them, puts them into their hand, then shuffles.")
_UNYARO = "At the beginning of your end step, if you planeswalked to Unyaro this turn, untap all creatures. They phase out until a player planeswalks."


def definition(ability: AbilityText, ch: Characteristics) -> Def | None:
    """A plane's line in one of the wordings of the module docstring; else None."""
    from app.rules import planar

    if not planar.planar(ch):
        return None
    text = ability.text.strip()
    if ability.kind == "static":
        if (kind := _PLAIN.get(text)) is not None:
            return {"kind": "static", "static": kind, "effects": []}
        if text == "Still Point in Time — All spells have split second.":  # Lake Silencio (207.2c flavor word)
            return {"kind": "static", "static": "spell_grant", "effects": [],
                    "spell_grants": [{"keyword": "split second", "filter": None, "all": True}]}
        if text == "Each creature card in your graveyard has embalm. Its embalm cost is equal to its mana cost.":  # Naktamun
            from app.rules import zone_grants

            d = zone_grants.define("each creature card in your graveyard has encore. its encore cost is equal to its mana cost")
            return {**d, "keyword": "embalm"} if d is not None and d.get("keyword") == "encore" else None
        if text == "If a creature would die, instead exile it and that creature's controller loses 2 life.":  # The Doctor's Tomb
            d = _native(ability, ch, "If a creature would die, exile it instead.")
            return {**d, "loses_e1": 2} if d is not None and d.get("static") == "exile_instead" and d.get("from") == "battlefield" else None
        if text == "The first spell you cast during each of your turns with mana value 2 or greater has cascade.":  # TARDIS Bay
            d = _native(ability, ch, "Spells you cast with mana value 2 or greater have cascade.")
            if d is None or d.get("static") != "spell_keyword" or d.get("keyword") != "cascade" or not d.get("filter") or d.get("first"):
                return None
            return {**d, "first": "kind", "during110c": "your_turn"}  # (cast_limits.granted_instances: first of that kind this turn, 601.2i)
        return None
    if ability.kind != "triggered":
        return None
    if text == _SQUIRRELS:  # We Hope You Like Squirrels: one ability, both trigger events (603.2); "that player": the upkeep's / the caster
        d = _native(ability, ch, "Whenever a player casts a spell, that player creates a 1/1 green Squirrel creature token.")
        step = _native(ability, ch, "At the beginning of each player's upkeep, that player creates a 1/1 green Squirrel creature token.")
        if d is None or step is None or d.get("trigger") != "event" or step.get("trigger") != "step:upkeep:each" or d["effects"] != step["effects"]:
            return None
        return {**d, "trigger": "multi:event+step:upkeep:each"}
    if (sea := _SEA.get(text)) is not None:  # Sea of Sand: the drawn card is revealed (its first static), so its kind is public
        from app.rules import selectors

        d = _native(ability, ch, sea[0])
        sel = selectors.parse(sea[1])
        if d is None or sel is None or (d.get("cond") or {}).get("event") != "draw":
            return None
        return {**d, "cond": {**d["cond"], "obj": sel.key()}}
    if text == _AMY:  # Amy's Home: "you may exile …" (an optional cost-like choice, the card bound: pay_objects), then suspended (702.62b)
        from dataclasses import replace

        from app.rules import planar

        d = planar.definition(replace(ability, text="When you planeswalk to Amy's Home and at the beginning of your upkeep, you may exile a "
                                                    "nonland card from your hand. If you do, draw a card."), ch)
        if d is None or [e.get("do") for e in d["effects"]] != ["optional_payment", "only_if", "draw"]:
            return None
        pay, only, _draw = d["effects"]
        return {**d, "effects": [pay, only, {"do": "suspend_found", "who": f"ref:{pay['bind']}", "n": 0, "per_card_mv": True}]}
    if text == _ENIGMA:  # Enigma Ridges: each player short of the most lands searches for up to the difference (``enigma``)
        from dataclasses import replace

        from app.rules import planar, scripts

        d = planar.definition(replace(ability, text="When you planeswalk to Enigma Ridges, you gain 1 life."), ch)
        parsed = scripts.parse_effects("search your library for up to two basic land cards, reveal them, put them into your hand, then shuffle.")
        if d is None or d.get("trigger") != "planar_to" or parsed is None or [e.get("do") for e in parsed[0]] != ["search"]:
            return None
        import copy

        return {**d, "effects": [{"do": "enigma_e1", "search": copy.deepcopy(parsed[0][0])}]}
    if text == _UNYARO:  # 603.4: an intervening "if" (the walk is recorded by ``on_events``); phasing until a player planeswalks (611.2a)
        d = _native(ability, ch, "At the beginning of your end step, if you attacked this turn, untap all creatures. They phase out.")
        if d is None or [e.get("do") for e in d["effects"]] != ["only_if", "untap", "phase_out"] or d.get("if") != {"history": "attacked"}:
            return None
        walked = {"history": "walked_here_e1"}
        only, untap, phase = d["effects"]
        return {**d, "if": walked, "effects": [{**only, "cond": walked}, untap, {**phase, "do": "phase_until_walk_e1"}]}
    return None


def _native(ability: AbilityText, ch: Characteristics, text: str) -> Def | None:
    import copy
    from dataclasses import replace

    from app.rules import scripts

    d = scripts.define(replace(ability, text=text), ch)
    return copy.deepcopy(d) if d is not None else None


# -- the face-up plane's statics --------------------------------------------------------------------------------------------------
def _face_defs(state: GameState, info: CardInfo | None, kind: str) -> list[tuple[CardInstance, Def]]:
    """(a face-up plane, each of its statics of ``kind``) for every face-up plane or phenomenon whose abilities work (901.11c: several
    can be face up at once, Spatial Merging; planar_statics.functions)."""
    pc = state.planechase
    if info is None or pc is None or pc.face_id is None:
        return []
    from app.game.handlers import planechase
    from app.rules import characteristics as chars
    from app.rules import planar_statics, scripts

    out: list[tuple[CardInstance, Def]] = []
    for fid in planechase.all_face_ids(pc):
        face = state.cards.get(fid)
        if face is None or not planar_statics.functions(state, face):
            continue
        out += [(face, d) for d in scripts.definitions(chars.of(face, info)).values() if d.get("kind") == "static" and d.get("static") == kind]
    return out


def extra_lands(state: GameState, player: str, info: CardInfo | None) -> int:
    """Naya (305.2): the planar controller may play any number of lands on their turn (a number no turn reaches)."""
    return 10**6 if any(face.controller == player for face, _ in _face_defs(state, info, ANY_LANDS)) else 0


def _attacked(state: GameState, player: str) -> bool:
    from app.game.rules_state import turn_log_now

    log = turn_log_now(state)
    return log is not None and bool(log.attackers.get(player))


def cast_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> str | None:
    """Prahv's "you can't cast spells" and Skybreen's prohibition (601.3), or None."""
    if any(face.controller == player for face, _ in _face_defs(state, info, PRAHV_CAST)) and _attacked(state, player):
        return "Prahv: you attacked with creatures this turn, so you can't cast spells"
    if _face_defs(state, info, TOP_TYPES):
        from app.game.state import zone_key
        from app.rules import characteristics as chars
        from app.rules.plan import live_players

        mine = CARD_TYPES & set(ch.types)
        for pid in live_players(state):
            lib = state.zones.get(zone_key(pid, "library")) or []
            if not lib or lib[0] == card.id:
                continue
            top = state.cards[lib[0]]
            shared = mine & set(chars.of(top, info).types) if info is not None else set()
            if shared:
                return f"Skybreen: spells that share a card type with the top card of a library can't be cast ({', '.join(sorted(shared))})"
    return None


def attack_problem(state: GameState, card: CardInstance, info: CardInfo | None) -> str | None:
    """Prahv: "If you cast a spell this turn, you can't attack with creatures." (508.1c), or None."""
    r = state.rules
    if r is None or not r.spells_this_turn(card.controller, state.turn.number):
        return None
    if any(face.controller == card.controller for face, _ in _face_defs(state, info, PRAHV_ATTACK)):
        return "Prahv: you cast a spell this turn, so you can't attack with creatures"
    return None


# -- untap steps (Horizon Boughs, Edge of Malacol) ---------------------------------------------------------------------------------
def untap_instead(plan: Plan, player: str, keep: list[str]) -> list[str]:
    """Edge of Malacol, as ``player``'s turn begins (they become the planar controller, 311.5): their tapped creatures that would untap
    (not already kept tapped) don't; recorded for ``untap_step``. The ids to keep tapped."""
    plan.rules.planar_more_e1.pop("malacol", None)
    if not _face_defs(plan.state, plan.info, UNTAP_COUNTERS) or player not in plan.live():
        return []
    held = [c for c in plan.state.cards.values() if c.zone == f"{player}:battlefield" and c.controller == player and c.tapped
            and c.id not in keep and not c.face_down and plan.ch(c).is_creature]
    if held:
        plan.rules.planar_more_e1["malacol"] = [plan.oid(c) for c in held]
    return [c.id for c in held]


def untap_step(plan: Plan) -> None:
    """In the active player's untap step (after their permanents untapped): Edge of Malacol's counters on the creatures held, then
    Horizon Boughs: every other player's tapped permanents untap (502.3)."""
    from app.rules import keyword_actions, replace, scripts

    held = plan.rules.planar_more_e1.pop("malacol", None) or []
    active = plan.active
    puts = [(c.id, "+1/+1", 2) for c in plan.state.cards.values()
            if c.zone.endswith(":battlefield") and c.controller == active and plan.oid(c) in held]
    if puts:
        plan.note("Edge of Malacol: two +1/+1 counters instead of untapping (614.1a)")
        try:
            replace.put_counters(plan, puts, by=active, then=None)
        except replace.Ask:  # (a choice among counter replacements: the counters go on as written, the players adjust by hand)
            plan.do({"type": "counter", "card_ids": [p[0] for p in puts], "kind": "+1/+1", "delta": 2}, actor=active)
    if not _face_defs(plan.state, plan.info, UNTAP_ALL):
        return
    live = set(plan.live())
    cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.tapped and c.controller != active
             and c.controller in live and "cant_untap" not in scripts.statics(plan.ch(c))]
    cards = keyword_actions.untap_stunned(plan, cards, active)  # 122.1d
    if cards:
        plan.note("Horizon Boughs: all permanents untap during each player's untap step")
        plan.do({"type": "tap", "card_ids": cards, "tapped": False}, actor=active)



# -- events: Sea of Sand's reveals, the walk Unyaro asks about, phasing until a player planeswalks ------------------------------------
def on_events(plan: Plan, events: list[Any]) -> None:
    """The table's "planar" events (planar.on_events): a planeswalk to a plane is recorded ("if you planeswalked to ~ this turn": the
    planar controller, that plane, this turn); a planeswalk (701.31: the ``from`` event, also one made by hand) ends Unyaro's phasing
    (the permanents phase in, 702.26). Sea of Sand: each card drawn is revealed (701.20) while it is face up."""
    on_walks(plan, events)
    draws = [e for e in events if e.kind == "drew" and e.card]
    if draws and _face_defs(plan.state, plan.info, REVEAL_DRAWS):
        for e in draws:
            card = plan.state.cards.get(e.card or "")
            if card is not None and card.zone.endswith(":hand"):
                plan.note(f"{plan.name(card.owner)} reveals {card.name} as they draw it (Sea of Sand)", [card.id])


def on_walks(plan: Plan, events: list[Any]) -> None:
    """The planeswalks among ``events`` (also called for a table action as the next engine action begins, as planar_chaos.on_events is:
    seeing the same events twice changes nothing)."""
    r = plan.rules
    for e in events:
        if e.kind != "planar":
            continue
        if e.counter == "to" and e.card:
            turn = plan.state.turn.number  # (901.11c: several planes may arrive at once: one record each, this turn's only)
            walked = [w for w in r.planar_more_e1.get("walked") or [] if isinstance(w, dict) and w.get("turn") == turn and w.get("card") != e.card]
            r.planar_more_e1["walked"] = [*walked, {"turn": turn, "card": e.card, "player": e.player}]
        if e.counter == "from" and any(p.until_walk_e1 for p in r.phase_lifetimes):
            from app.rules import phase_lifetimes43

            phase_lifetimes43._release(plan, [p for p in r.phase_lifetimes if p.until_walk_e1])


def walked_here(plan: Plan, ctx: dict[str, Any]) -> bool:
    """Unyaro: "if you planeswalked to ~ this turn" — the planar controller planeswalked to this plane (its object) this turn."""
    return any(isinstance(w, dict) and w.get("turn") == plan.state.turn.number and w.get("card") == ctx.get("source_card")
               and w.get("player") in (None, ctx.get("controller")) for w in plan.rules.planar_more_e1.get("walked") or [])


def phase_until_walk(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Unyaro: "They phase out until a player planeswalks." (702.26a; ruling 2023-04-14: they don't phase in during the untap step) — a
    phasing packet held until ``on_events`` sees a planeswalk, whatever happens to the plane."""
    from app.game.rules_state import ObjectRef, PhaseLifetime
    from app.rules import effects

    ids = [cid for cid in effects._cards(plan, ctx, e["who"])
           if (c := plan.state.cards.get(cid)) is not None and plan.in_game(c) and c.zone.endswith(":battlefield")]
    if not ids:
        return True
    refs = [ObjectRef(card=cid, object_id=plan.oid(plan.state.cards[cid]), zone=plan.state.cards[cid].zone) for cid in ids]
    packet = PhaseLifetime(source=ObjectRef(card=ctx.get("source_card") or "", object_id=ctx.get("source_object") or ""), recipients=refs,
                           until_walk_e1=True)
    plan.rules.phase_lifetimes.append(packet)
    plan.do({"type": "phase_shift", "card_ids": ids, "out": True}, actor=ctx["controller"])
    packet.recipients = [x for x in refs if (c := plan.state.cards.get(x.card)) is not None and plan.oid(c) == x.object_id
                         and c.zone.endswith(":phased") and not c.phased_indirect]
    return True


def enigma(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Enigma Ridges: the land counts as it resolves (608.2h); each player with fewer lands than the most searches, in turn order (101.4),
    for up to the difference ("as_player": "your library" is theirs), reveals them, puts them into their hand and shuffles."""
    import copy

    live = plan.apnap()
    lands = {p: sum(1 for c in plan.state.cards.values() if c.zone == f"{p}:battlefield" and c.controller == p and plan.ch(c).is_land)
             for p in live}
    most = max(lands.values(), default=0)
    added: list[Def] = []
    for p in live:
        if (short := most - lands[p]) > 0:
            added += [{"do": "as_player", "player": p}, {**copy.deepcopy(e["search"]), "max": short}, {"do": "as_player_end"}]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    return True


PRIMITIVES: dict[str, Any] = {"phase_until_walk_e1": phase_until_walk, "enigma_e1": enigma}
