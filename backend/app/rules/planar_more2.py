"""-- planechase more 2 (wave F1) -- the face-up plane's remaining lines, each in its exact Oracle wording, read as the nearest native ability
with a small dedicated rule where the engine has none (CR 311.4, 113.6p: its abilities work face up in the command zone; "you" is the planar
controller, 311.5; 901.11c: every face-up plane is an object, each read: ``planar_more._face_defs``). The collectors call in here with one
line each, marked ``wave F1``.

Statics:

* Grixis: "Blue, black, and/or red creature cards in your graveyard have unearth. The unearth cost is equal to the card's mana cost." — the
  zone_grants grant (as Naktamun's embalm) for unearth (702.84a); ruling 2009-10-01: the ability is the card's own, its cost the card's mana
  cost including its color.
* Otaria: "Instant and sorcery cards in graveyards have flashback. The flashback cost is equal to the card's mana cost." — the native
  ``gy_flashback`` for every graveyard (``any_owner_f1``: its owner may cast it, 702.34a); ruling 2021-03-19: no mana cost, no flashback.
* Strixhaven: "Instant and sorcery spells players cast have demonstrate." — the native demonstrate grant for every caster (``players_f1``,
  702.144a).
* Trail of the Mage-Rings: "Instant and sorcery spells have rebound." — the native rebound replacement (702.88a) for every controller
  (``rebound_all``; ruling 2013-04-15: the upkeep cast still happens after the plane is gone, the native ``rebounding`` record).
* The Caldaia: "Creature spells you cast from your hand have blitz {3}." — a table alternative cost (702.152a, tag ``blitz``: haste, the
  draw-when-it-dies and the end-step sacrifice follow from the tag) for a creature spell cast from the planar controller's hand.
* Windriddle Palaces: "You may play lands and cast spells from the top of any player's library." — the native top-of-library permission for
  the top card of every library (``any_library_f1``; rulings 2012-06-01: only the planar controller, normal timing, a land is the land play).
* The Golden City of Orazca: "Ascend" — ruling 2023-04-14: on a plane it is a static ability (702.131b), not a trigger: the planar controller
  gets the city's blessing at once when they control ten permanents (``ascend_face``, read by designations.ascend_permanent_due).
* Talon Gates: "Any time you could cast a sorcery, you may exile a nonland card from your hand with X time counters on it, where X is its
  mana value. If the exiled card doesn't have suspend, it gains suspend." — a special action (ruling 2012-06-01: no stack, any number of
  times): each nonland card in the planar controller's hand is given the action's line (``TALON_LINE``, index 100+, zone_grants.apply) and
  taking it is the native suspend special action with no cost and X time counters (special_payment_tails ``suspend``, 702.62b).

Triggers:

* Furnace Layer: "select target player at random" — a target all the same (115.1), picked by the table as the ability goes on the stack, each legal
  player equally likely (the native ``random`` target group, Scab-Clan Giant ruling 2013-04-15; Furnace Layer ruling 2012-06-01: you can be
  selected; an empty hand: nothing happens), recorded for replays.
* Ghirapur / New New York: "… becomes a 5/3 Vehicle in addition to its other types and gains trample, haste, and crew 2." — the native ``become``
  (613.1d: the Vehicle subtype added; 613.1f: the keywords and crew N; 613.4b: the P/T, which matter once crewed, 702.122) on the artifacts as the
  ability resolves (ruling 2023-04-14), until end of turn.
* Grand Ossuary: "its controller distributes … among any number of target creatures they control" — ruling 2012-06-01: the ability's controller
  (the planar controller) chooses the targets and the division as it is put on the stack (601.2c-d, at least one each); the targets are creatures
  the dead creature's controller controls (bound as it triggers: ``bind``), the number its power as it last existed (608.2h); that player puts them.
* Kharasha Foothills: myriad's procedure (702.116a: one private yes / no per other opponent, the copies at once) for "that creature", each copy
  tapped and attacking only that opponent (ruling 2012-06-01: never a planeswalker), exiled at the next end step (the native delayed exile).
* Glen Elendra: the native optional exchange (701.12b) whose targets are related through this combat's combat damage (``on_events`` records it,
  510.2; ``glen_options`` filters the targets, ``glen_exchange`` re-checks the second as it resolves; ruling 2012-06-01: an illegal target, no
  exchange).
* Glimmervoid Basin: "with a single target" (rulings 2009-10-01: exactly one target chosen once) — the caster copies the spell for each other
  legal target of any kind as if cast anew (707.10d; the original target excluded), ordering the copies (copying._each_run); the copies aren't cast.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

Def = dict[str, Any]

REBOUND_ALL = "rebound_all_f1"
TALON = "talon_f1"
TALON_LINE = ("Talon Gates — Exile this card from your hand with X time counters on it, where X is its mana value. If it doesn't have suspend, "
              "it gains suspend. Activate only as a sorcery.")
STATIC_KINDS = frozenset({REBOUND_ALL, "gy_flashback", "alt_cost"})

_GRIXIS = "Blue, black, and/or red creature cards in your graveyard have unearth. The unearth cost is equal to the card's mana cost."
_OTARIA = "Instant and sorcery cards in graveyards have flashback. The flashback cost is equal to the card's mana cost."
_STRIX = "Instant and sorcery spells players cast have demonstrate."
_TRAIL = "Instant and sorcery spells have rebound."
_CALDAIA = "Creature spells you cast from your hand have blitz {3}."
_WINDRIDDLE = "You may play lands and cast spells from the top of any player's library."
_FURNACE = ("When you planeswalk to Furnace Layer and at the beginning of your upkeep, select target player at random. That player discards a card. "
            "If that player discards a land card this way, they lose 3 life.")
_FURNACE_NATIVE = ("When you planeswalk to Furnace Layer and at the beginning of your upkeep, target player discards a card. If a land card is discarded "
                   "this way, that player loses 3 life.")
_VEHICLES = {  # the line: (the native wording read for the trigger, the artifacts, P/T, keywords, crew N)
    "At the beginning of combat on your turn, until end of turn, each noncreature, non-Vehicle artifact you control becomes a 5/3 Vehicle in addition to its "
    "other types and gains trample, haste, and crew 2.": (
        "At the beginning of combat on your turn, until end of turn, each noncreature artifact you control becomes a 5/3 artifact creature in addition to "
        "its other types and gains trample and haste.", "noncreature, non-Vehicle artifact you control", 5, 3, ("trample", "haste"), 2),
    "At the beginning of combat on your turn, until end of turn, noncreature artifacts you control become 3/3 Vehicles in addition to their other types "
    "and gain flying, haste, and crew 1.": (
        "At the beginning of combat on your turn, until end of turn, noncreature artifacts you control become 3/3 artifact creatures in addition to "
        "their other types and gain flying and haste.", "noncreature artifact you control", 3, 3, ("flying", "haste"), 1),
}
_UNBOUND = "player:ossuary_f1"  # (Grand Ossuary's "they control" before the trigger is put on the stack)
_OSSUARY = ("Whenever a creature dies, its controller distributes a number of +1/+1 counters equal to its power among any number of target creatures "
            "they control.")
_KHARASHA = ("Whenever a creature you control attacks a player, for each other opponent, you may create a token that's a copy of that creature, tapped "
             "and attacking that opponent. Exile those tokens at the beginning of the next end step.")
_GLEN = ("At end of combat, you may exchange control of target creature you control that dealt combat damage to a player this combat and target creature "
         "that player controls.")
_GLIMMER = ("Whenever a player casts an instant or sorcery spell with a single target, that player copies that spell for each other spell, permanent, card "
            "not on the battlefield, and/or player the spell could target. Each copy targets a different one of them.")
_TALON = ("Any time you could cast a sorcery, you may exile a nonland card from your hand with X time counters on it, where X is its mana value. "
          "If the exiled card doesn't have suspend, it gains suspend.")


def definition(ability: AbilityText, ch: Characteristics) -> Def | None:
    """A plane's line in one of the wordings of the module docstring; else None."""
    from app.rules import planar
    from app.rules.planar_more import _native

    if not planar.planar(ch):
        return None
    text = ability.text.strip()
    if ability.kind == "static":
        if text == _GRIXIS:  # (the colors read as "blue, black, or red": 105.2, a card of any of them)
            from app.rules import selectors

            sel = selectors.parse("blue, black, or red creature card in your graveyard")
            if sel is None or sel.zones != ("graveyard",):
                return None
            return {"kind": "static", "static": "zone_grant", "filter": sel.key(), "keyword": "unearth", "cost": None, "reduce": 0, "effects": []}
        if text == _OTARIA:  # (any graveyard: the card's owner casts it from their own, 702.34a)
            d = _native(ability, ch, "Each instant and sorcery card in your graveyard has flashback. The flashback cost is equal to its mana cost.")
            return {**d, "any_owner_f1": True} if d is not None and d.get("static") == "gy_flashback" and not d.get("your_turn") else None
        if text == _STRIX:  # (every caster: "players cast")
            d = _native(ability, ch, "Instant and sorcery spells you cast have demonstrate.")
            return {**d, "players_f1": True} if d is not None and d.get("static") == "spell_keyword" and d.get("keyword") == "demonstrate" else None
        if text == _TRAIL:
            d = _native(ability, ch, "Instant and sorcery spells you control have rebound.")
            return {"kind": "static", "static": REBOUND_ALL, "effects": []} if d is not None and d.get("static") == "rebound100d" else None
        if text == _CALDAIA:  # (as zone_grants._warp: a table alternative cost for a spell cast from its caster's hand)
            from app.rules.permissions import spell_filter

            key = spell_filter("creature")
            return None if key is None else {"kind": "static", "static": "alt_cost", "cost": "pay {3}", "table": True, "filter": None, "filters": [key],
                                             "once": False, "zone": "hand", "mv": None, "cond": None, "tag": "blitz", "effects": []}
        if text == _WINDRIDDLE:
            return {"kind": "static", "static": "permission", "zone": "library_top", "once": False, "flash": False, "self": False, "play": True,
                    "cast": True, "filter": None, "any_library_f1": True, "effects": []}
        if text == _TALON:  # (the line each nonland card in the planar controller's hand is given: zone_grants.apply)
            from app.rules import selectors

            sel = selectors.parse("nonland card in your hand")
            return None if sel is None else {"kind": "static", "static": "zone_grant", "filter": sel.key(), "keyword": TALON, "cost": None, "reduce": 0,
                                             "effects": []}
        return None
    if ability.kind != "triggered":
        return None
    if text == _FURNACE:  # 115.1 / Scab-Clan Giant ruling 2013-04-15: a target all the same, picked at random by the table as the ability goes on the stack
        from dataclasses import replace

        d = planar.definition(replace(ability, text=_FURNACE_NATIVE), ch)  # (ruling 2012-06-01: any player, you too; no card: nothing happens)
        if d is None or d.get("trigger") != "multi:planar_to+upkeep_you" or d.get("target") != {"what": "player"}                 or [e.get("do") for e in d["effects"]] != ["discard", "only_if", "lose_life"]:
            return None
        return {**d, "target": None, "targets": [{"what": "player", "min": 1, "max": 1, "random": True}]}
    if (vehicle := _VEHICLES.get(text)) is not None:  # Ghirapur, New New York (613.1d / 613.1f / 613.4b; ruling 2023-04-14: the set is fixed as it resolves)
        native, sel_text, p, t, keywords, crew = vehicle
        d = _native(ability, ch, native)
        from app.rules import selectors

        sel = selectors.parse(sel_text)
        if d is None or sel is None or d.get("trigger") != "step:begin_combat:you" or [e.get("do") for e in d["effects"]] != ["become", "grant"]:
            return None
        become = d["effects"][0]
        if become.get("p") != p or become.get("t") != t or become.get("duration") != "end_of_turn":
            return None
        return {**d, "effects": [{"do": "become", "who": sel.key(), "types": ["Artifact"], "retain": True, "add_creature_types": ["Vehicle"], "p": p, "t": t,
                                  "keywords": list(keywords), "abilities": [f"Crew {crew}"], "duration": "end_of_turn",
                                  "label": f"a {p}/{t} Vehicle with {', '.join(keywords)} and crew {crew}"}]}
    if text == _OSSUARY:  # Grand Ossuary (ruling 2012-06-01: the ability's controller chooses the targets and the division as it is put on the stack,
        # 601.2c-d, at least one counter each; an illegal target's counters are lost): creatures the dead creature's controller controls (bound with
        # the event, ``bind``), its power as it last existed (608.2h); the dead creature's controller distributes them ("by", 122.6)
        d = _native(ability, ch, "Whenever a creature dies, distribute X +1/+1 counters among any number of target creatures you control, where X is the "
                                 "number of creatures you control.")
        if d is None or len(d.get("targets") or []) != 1 or [e.get("do") for e in d["effects"]] != ["add_counters"]:
            return None
        group = d["targets"][0]
        from app.rules import selectors

        sel = selectors.parse("creature")
        if sel is None or not group.get("divide") or group["divide"].get("what") != "counters":
            return None
        what = selectors.replace(sel, controller=_UNBOUND).key()  # (no player until ``bind``: nothing matches)
        return {**d, "ossuary_f1": True, "targets": [{**group, "what": what, "divide": {**group["divide"], "value": {"power": "event"}}}],
                "effects": [{**d["effects"][0], "by": "ref:event.controller"}]}
    if text == _KHARASHA:  # Kharasha Foothills: myriad's procedure (702.116a) for "that creature", only the players (ruling 2012-06-01: no planeswalker)
        d = _native(ability, ch, "Whenever a creature you control attacks a player, create a token that's a copy of that creature. Exile it at the "
                                 "beginning of the next end step.")
        if d is None or [e.get("do") for e in d["effects"]] != ["token_copy", "delayed", "deferred:exile"] or (d.get("cond") or {}).get("defender") != "player":
            return None
        made, later, gone = d["effects"]
        return {**d, "effects": [{"do": "kharasha_choose_f1"}, {"do": "kharasha_create_f1", "who": made["who"], "as": made["as"]}, later, gone]}
    if text == _GLEN:  # Glen Elendra: the native exchange (701.12b; ruling 2012-06-01: either target illegal, no exchange) with the two relations of its
        # targets read from this combat's combat damage (``glen_options``; "that player": the player the first target dealt combat damage to)
        d = _native(ability, ch, "At end of combat, you may exchange control of target creature you control and target creature an opponent controls.")
        if d is None or len(d.get("targets") or []) != 2 or [e.get("do") for e in d["effects"]] != ["exchange_control"] or not d.get("optional"):
            return None
        first, second = d["targets"]
        return {**d, "targets": [{**first, "glen_f1": 0}, {**second, "glen_f1": 1}], "effects": [{**d["effects"][0], "do": "glen_exchange_f1"}]}
    if text == _GLIMMER:  # Glimmervoid Basin (rulings 2009-10-01): only a spell with exactly one target, chosen once (``single_f1``); a copy for each
        # other legal target of any kind as if cast anew (707.10d), controlled by the caster, who orders them; the copies aren't cast
        d = _native(ability, ch, "Whenever a player casts an instant or sorcery spell, copy it.")
        if d is None or d.get("trigger") != "event" or (d.get("cond") or {}).get("event") != "cast":
            return None
        return {**d, "cond": {**d["cond"], "targets": "single_f1"}, "effects": [{"do": "glimmer_f1"}]}
    return None


# -- the collectors' readers ---------------------------------------------------------------------------------------------------------------
def rebound_all(plan: Plan) -> bool:
    """Trail of the Mage-Rings: a face-up plane gives every instant and sorcery spell rebound (702.88a), whoever controls it."""
    from app.rules.planar_more import _face_defs

    return bool(_face_defs(plan.state, plan.info, REBOUND_ALL))


def ascend_face(plan: Plan, pid: str) -> bool:
    """The Golden City of Orazca: ``pid`` is the controller of a face-up plane with ascend (702.131b; ruling 2023-04-14: on a plane it is a
    static ability)."""
    pc = plan.state.planechase
    if pc is None or pc.face_id is None:
        return False
    from app.game.handlers import planechase
    from app.rules import planar_statics

    for fid in planechase.all_face_ids(pc):
        face = plan.state.cards.get(fid)
        if face is not None and face.controller == pid and planar_statics.functions(plan.state, face) and any(
                ab.kind == "keywords" and "ascend" in ab.keywords for ab in plan.ch(face).abilities):
            return True
    return False


def bind(plan: Plan, t: Any) -> None:
    """Grand Ossuary, as its trigger is put on the stack (603.3d): "creatures they control" are the dead creature's controller's — as it last existed
    on the battlefield (its snapshot, 608.2h). Unbound (no legal target) when that isn't known."""
    if not t.ability.get("ossuary_f1") or t.event is None or len(t.event.objects) != 1:
        return
    import json

    ref = t.event.objects[0]
    snap = ref.snapshot or plan.rules.lki.get(ref.object_id)
    who = getattr(snap, "controller", None)
    if not who:
        return
    raw = json.dumps(t.ability).replace(f'\\"controller\\":\\"{_UNBOUND}\\"', f'\\"controller\\":\\"player:{who}\\"')
    t.ability = json.loads(raw)


def keyword_ok(feature_id: str) -> bool:
    """The keywords of a plane a collector reads (coverage): ascend (``ascend_face``)."""
    return feature_id == "keyword:ascend"


def talon_ability(ability: Any) -> bool:
    return ability is not None and ability.index >= 100 and ability.text == TALON_LINE


def talon(plan: Plan, card: CardInstance, ch: Characteristics, a: Any) -> None:
    """Talon Gates' special action (ruling 2012-06-01; 116.2): any time its owner could cast a sorcery (307.1), the card goes from their hand to
    exile with X time counters, X its mana value, and is suspended (it gains suspend if it doesn't have it: special_payment_tails)."""
    from app.game.errors import ActionError
    from app.game.state import STACK, zone_key
    from app.rules import casting, special_payment_tails
    from app.rules import mana as M
    from app.rules.casting import Purpose

    state = plan.state
    if card.zone != zone_key(plan.actor, "hand") or card.owner != plan.actor or "Land" in ch.types:
        raise ActionError("Talon Gates: only a nonland card from your hand")
    if state.turn.active_player != plan.actor or state.turn.phase not in casting.MAIN_PHASES or state.zones.get(STACK):
        raise ActionError("Talon Gates: only any time you could cast a sorcery (your main phase, the stack empty)")
    n = int(ch.mana_value)
    special_payment_tails.pay(plan, "suspend", card, ch, M.parse_cost("{0}"), f"Talon Gates: exiles {ch.name} with {n} time counters",
                              sources=list(getattr(a, "sources", None) or []), purpose=Purpose(), number=n, original_cost="{0}")


# -- Glen Elendra: this combat's combat damage to players -------------------------------------------------------------------------------------------
def on_events(plan: Plan, events: list[Any]) -> None:
    """Every event batch (planar.on_events): the combat damage dealt to players in this combat phase (510.2; a new combat phase starts afresh), as
    (the source object, the player) pairs. Recorded only in a Planechase game."""
    if plan.state.planechase is None:
        return
    hits = [[e.source, e.player] for e in events if e.kind == "damage" and e.combat and e.player and e.source and e.amount > 0 and not e.manual]
    if not hits:
        return
    store = plan.rules.planar_more2_f1
    now = {"turn": plan.state.turn.number, "combat": plan.rules.combats}
    old = store.get("combat_damage") or {}
    dealt = list(old.get("dealt") or []) if all(old.get(k) == v for k, v in now.items()) else []
    store["combat_damage"] = {**now, "dealt": dealt + [h for h in hits if h not in dealt]}


def _damaged(plan: Plan, oid: str) -> list[str]:
    """The players the object ``oid`` dealt combat damage to in this combat phase."""
    rec = plan.rules.planar_more2_f1.get("combat_damage") or {}
    if rec.get("turn") != plan.state.turn.number or rec.get("combat") != plan.rules.combats:
        return []
    return [p for src, p in rec.get("dealt") or [] if src == oid]


def glen_options(plan: Plan, spec: Def, options: list[str], groups: list[list[str]]) -> list[str]:
    """Glen Elendra's targets (601.2c): the first, a creature you control that dealt combat damage to a player this combat; the second, a creature
    controlled by the player the first one dealt combat damage to."""
    if spec.get("glen_f1") == 0:
        return [t for t in options if t in plan.state.cards and _damaged(plan, plan.oid(plan.state.cards[t]))]
    first = groups[0] if groups else []
    if len(first) != 1 or first[0] not in plan.state.cards:
        return []
    players = set(_damaged(plan, plan.oid(plan.state.cards[first[0]])))
    return [t for t in options if t in plan.state.cards and plan.state.cards[t].controller in players]


def glen_exchange(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """608.2b as it resolves: the second target is still controlled by a player the first dealt combat damage to this combat; else that target is
    illegal and no exchange happens (ruling 2012-06-01)."""
    from app.rules import effects

    mine, theirs = effects._cards(plan, ctx, e["who"]), effects._cards(plan, ctx, e["with"])
    if len(mine) != 1 or len(theirs) != 1:
        return True
    if plan.state.cards[theirs[0]].controller not in _damaged(plan, plan.oid(plan.state.cards[mine[0]])):
        plan.note(f"{ctx.get('name') or 'Glen Elendra'}: no exchange (that creature's controller wasn't dealt combat damage by the other)")
        return True
    return bool(effects.PRIMITIVES["exchange_control"](plan, ctx, {**e, "do": "exchange_control"}))


# -- Glimmervoid Basin ---------------------------------------------------------------------------------------------------------------------------------
def single_target(targets: list[tuple[str, str | None]]) -> bool:
    """"with a single target" (rulings 2009-10-01): exactly one target, chosen once (not one object targeted twice, not several)."""
    return len(targets) == 1


def glimmer(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """The spell's caster copies it for each other player or object its one target could be now (707.10d, 115.1: any zone the target word allows),
    each copy targeting a different one (copying._each_run: its controller orders them, 707.10c). A spell that left the stack is copied as it last
    was there; a spell the engine can't copy, or whose target isn't a single plain one now, is copied by hand."""
    from app.rules import copying, spell_copy_replacements, targets

    found = next(iter(copying._copy_sources(plan, ctx, "event_spell")), None)
    if found is None:
        return copying._manual_each(plan, ctx, ctx["controller"], None) if copying._event_object_left(ctx, "event_spell") else True
    source, oid = found
    card = plan.state.cards.get(source)
    entry = copying.source_entry102(plan, card, oid) if card is not None else None
    if card is None or entry is None:
        return True
    reason = copying.uncopyable(plan, card, object_id=oid)
    if reason is not None:
        return True if not reason else copying._manual_each(plan, ctx, entry.controller, card)
    pos = copying.positions(entry)
    if len(pos) != 1:
        return copying._manual_each(plan, ctx, entry.controller, card)
    caster = entry.controller
    old = {t.id for t in entry.targets} | {r.id for g in entry.groups for r in g} | {r.id for g in entry.slots for r in g}
    source_ch = targets.source_of(plan, source, True, object_id=oid)
    victims = []
    for v in targets.legal_targets(plan, copying._spec(entry, pos[0]).get("what", "any"), caster, source_ch, source, source_object=oid):
        if v in old or v == source:
            continue
        probe = copying._retargeted(entry, pos, [targets.ref(plan, v)])
        probe.controller = caster
        if copying._problem(plan, probe) is None:
            victims.append(v)
    if not victims:
        return True
    return copying._each_run(plan, {"ctx": ctx, "spell": source, "oid": oid, "controller": caster, "victims": victims,
                                    "additional": spell_copy_replacements.additional(plan, caster)})


# -- Kharasha Foothills ------------------------------------------------------------------------------------------------------------------------
def kharasha_choose(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"for each other opponent, you may …": one private yes / no per opponent other than the player that creature attacks (as myriad's,
    combat_rules._myriad_next; the answers are recorded in the resolution context)."""
    from app.rules import combat_rules, effects

    me = ctx["controller"]
    ctx["myriad"] = []
    event = ctx.get("event") or {}
    attacked = event.get("defended") or next(iter(event.get("attacked_players") or []), None)
    if attacked is None:
        ids = effects._cards(plan, ctx, "event")
        card = plan.state.cards.get(ids[0]) if ids else None
        attacked = card.attacking.id if card is not None and card.attacking is not None and card.attacking.kind == "player" else None
    if attacked is None or plan.state.turn.phase not in ("declare_attackers", "declare_blockers", "combat_damage", "end_combat"):
        return True  # (no longer in combat: a token can't enter attacking, 506.3)
    return combat_rules._myriad_next(plan, ctx, [p for p in plan.apnap() if p not in (me, attacked) and p in plan.live()], [])


def kharasha_create(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """The copies (707.2: the copiable values; 111.10 none of its counters or effects) at once, tapped, each attacking the player it was made for
    (508.4: not declared as an attacker; only that player — ruling 2012-06-01: not a planeswalker)."""
    from app.rules import context, copying, replace, token_attack_continuations
    from app.rules.token_grammar import _attack_with

    players = [p for p in ctx.get("myriad") or [] if p in plan.live()]
    if not players:
        return True
    ctx.pop(token_attack_continuations.BINDING, None)
    if not copying.token_copy(plan, ctx, {"do": "token_copy", "who": e["who"], "n": 1, "tapped": True, "as": e.get("as"), "creation_recipients": players,
                                          "receipt_bind": token_attack_continuations.BINDING}, then=replace.rerun_then(ctx, e)):
        return False
    for raw in ctx.pop(token_attack_continuations.BINDING, None) or []:
        atom = token_attack_continuations.CreatedAtom.model_validate(raw)
        pid = atom.atom.removeprefix("opponent:")
        for ref in atom.objects:
            token = context._same(plan, ref)
            if token is not None and token.zone.endswith(":battlefield") and pid in plan.live() and token.controller == plan.active                     and "Creature" in plan.ch(token).types and plan.state.turn.phase in ("declare_attackers", "declare_blockers", "combat_damage", "end_combat"):
                _attack_with(plan, [token.id], pid, token.controller)
    return True


PRIMITIVES: dict[str, Any] = {"kharasha_choose_f1": kharasha_choose, "kharasha_create_f1": kharasha_create, "glen_exchange_f1": glen_exchange,
                              "glimmer_f1": glimmer}
RESUME: dict[str, Any] = {}
