"""Continuous effects and the layer system (CR 611, 613), researched against CR 2026-09-25.

Two kinds of continuous effect meet here:

* effects of resolved spells and abilities (``rules.effects``): they name the **rules objects** they
  affect, locked when they begin (611.2c); an affected permanent that changes zones is a new object
  and the effect no longer applies to it (400.7);
* effects of static abilities of permanents (app/rules/statics.py: anthems, lords, "as long as"
  grants, Auras' and Equipment's "Enchanted/Equipped creature gets …"): never locked in — they apply
  "at any given moment to whatever [their] text indicates" (611.3a), while the source is on the
  battlefield (611.3b), so they affect objects that enter later and follow a change of control of
  the source ("you" is its controller).

Printed characteristics are never overwritten: ``derive`` computes the current ones each time from
the printed card. Layers implemented (each with tests): 4 (types added, e.g. a crewed Vehicle;
subtypes added, an amassed Army's, 701.47a),
6 (abilities: keywords gained / lost, quoted abilities granted, 613.1f), 7a (characteristic-defining
abilities the static grammar reads — "~'s power is equal to the number of …" — computed in every
zone, 604.3 / 613.4a; any other ``*`` stays unknown), 7b (setting effects, incl. "base power
and toughness", 613.4b), 7c (modifying effects **and counters**, 613.4c, incl. "gets +1/+1 for each
…" read whenever the characteristics are, 611.3a), 7d (switching). Within a
layer, effects apply in timestamp order (613.7): a resolved effect's is handed out when it begins
(613.7b), a static ability's is its source's — the object number it got when it entered (613.7a,
613.7d; ``RulesState.objects``), or the granting object's if later for a granted ability — and the
two are interleaved through ``ContinuousEffect.object_seq`` (the last object to enter before the
effect began). An Aura, Equipment or Fortification gets a new timestamp as it becomes attached
(613.7e), a permanent as it turns face up or down (613.7f) and a double-faced permanent as it
transforms (613.7g): ``RulesState.restamped``, read by ``timestamp``. Not tracked: APNAP order
among simultaneous entries (613.7m: creation order is used).
Dependencies (613.8): a static's subject is read from the object after layer 4 and the resolved
layer-6 effects; a subject that asks about keywords ("creatures with flying …") is read again once
layer 6 is applied, until nothing changes — other dependencies (types, power) aren't modelled.
Layers 1–5 (copy, control, text, color) are next; the model already carries the layer number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

from app.game.rules_state import ContinuousEffect
from app.game.state import CardInstance, GameState
from app.rules.characteristics import CardInfo, Characteristics

if TYPE_CHECKING:
    from app.rules.plan import Plan


def _num(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def affecting(state: GameState, card: CardInstance) -> list[ContinuousEffect]:
    r = state.rules
    if r is None or not r.effects or not card.zone.endswith(":battlefield"):
        return []
    oid = r.object_id(card.id)
    return sorted((e for e in r.effects if oid in e.affected), key=lambda e: e.timestamp)


@dataclass(frozen=True)
class Static:
    """One static ability's continuous effect, as found on the battlefield."""

    source: str  # the permanent whose ability it is
    controller: str
    definition: dict[str, Any]
    # Its timestamp (613.7a): its source's, i.e. the object number the source got when it entered
    # (613.7d; ``RulesState.objects``) — or, for an ability another static grants, the granting
    # object's if that is later.
    seq: int
    gate: tuple[str, dict[str, Any]] | None = None  # (granting permanent, its static) for a granted ability


_STATIC_CACHE: dict[tuple, list[Static]] = {}


def timestamp(state: GameState, card_id: str) -> int:
    """A permanent's timestamp: the object number it got as it entered (613.7d), or the later one
    it received since — as an Aura, Equipment or Fortification that became attached (613.7e), as
    it turned face up or down (613.7f) or as a double-faced permanent that transformed (613.7g;
    ``RulesState.restamped``)."""
    r = state.rules
    if r is None:
        return 0
    return max(r.objects.get(card_id, 0), r.restamped.get(card_id, 0))


def statics(state: GameState, info: CardInfo) -> list[Static]:
    """Static grants and attached rules of permanents on the battlefield, read from printed
    abilities and from abilities other statics grant; cached by what is on the battlefield, in
    timestamp order. Whether each applies to a given object, and its conditions, are evaluated
    by ``derive``."""
    r = state.rules
    live = {p for p in state.seat_order if not state.players[p].left} - (set(r.conceded) | set(r.lost) if r else set())
    # -- copy system (wave 2F): statics are read from copiable values (613.2c: a Clone of an anthem
    # has the anthem's ability), so which copy effect applies to each permanent is part of the key
    from app.rules.copying import copy_index

    copies = copy_index(r)
    # (the face and flip state are part of the key: a transformed permanent has only its back
    # face's characteristics, 712.8e — its front face's statics are gone, 611.3a)
    key = tuple(sorted((cid, c.controller, c.face_down, c.face, c.flipped, c.card_id or c.name, c.token.text if c.token else "",
                        r.card_mode(cid) if r else "", timestamp(state, cid),
                        copies.get(r.object_id(cid), (0, "")) if r else (0, ""))
                       for cid, c in state.cards.items() if c.zone.endswith(":battlefield")))
    hit = _STATIC_CACHE.get(key)
    if hit is not None:
        return hit
    from app.rules import scripts
    from app.rules import statics as grammar

    field = [(cid, c) for cid, c in state.cards.items()
             if c.zone.endswith(":battlefield") and not c.face_down and c.controller in live and c.owner in live
             and not (r is not None and r.card_mode(cid) == "manual")]
    out = []
    for cid, c in field:
        for d in scripts.definitions(copiable(state, c, info)).values():
            if d["kind"] == "static" and d.get("static") in ("grant", "attached_rule"):
                out.append(Static(cid, c.controller, d, timestamp(state, cid)))
    # An ability a static grants may itself be a static ("Commander creatures you own have
    # "Creature tokens you control get +2/+2.""): it works on whatever it's granted to, with the
    # later of the two timestamps (613.7a), while the granting static applies to that object.
    for st in list(out):
        if st.definition["static"] != "grant":
            continue
        for text in st.definition.get("grants", ()):
            inner = grammar.parse(scripts.self_text(text, ""))
            if inner is None:
                continue
            for cid, c in field:
                out.append(Static(cid, c.controller, inner, max(st.seq, timestamp(state, cid)),
                                  gate=(st.source, st.definition)))
    out.sort(key=lambda st: st.seq)
    if len(_STATIC_CACHE) > 256:
        _STATIC_CACHE.clear()
    _STATIC_CACHE[key] = out
    return out


anthems = statics  # (the old name)


# -- copy system (wave 2F): layer 1 (613.2) -----------------------------------------------------------
def copiable(state: GameState, card: CardInstance, info: CardInfo) -> Characteristics:
    """613.2c: the object's copiable values — its printed values (for a token or a copy, what the
    effect that created it defined, 613.1), then layer 1: copy effects (613.2a), face-down status
    (613.2b). What a copy copies (707.2) and what static abilities are read from."""
    from app.rules import characteristics as chars
    from app.rules.copying import layer1

    return layer1(state, card, chars.of(card, info), info)


def _view(state: GameState, info: CardInfo) -> Plan:
    """A read-only view of this table (no copy) for the selector / condition evaluators."""
    from app.rules.plan import Plan

    view = Plan.__new__(Plan)
    view.state, view.info = state, info
    return view


_depth = 0  # re-entrancy: a static's subject or condition reading another object's characteristics
_COND_CACHE: dict[tuple, bool] = {}


def _table_key(state: GameState) -> tuple:
    """Everything a static's condition or dynamic amount ("for each …", a CDA's count) may read
    (611.3a: checked whenever it's looked at), so one verdict per static serves a whole pass over
    the table: life, hands, graveyards and exile (which cards: "creature cards in your graveyard"),
    players' counters, the permanents with their status and counters, and the resolved effects."""
    r = state.rules
    players = tuple((pid, state.players[pid].life, len(state.zones.get(f"{pid}:hand", ())),
                     tuple(state.zones.get(f"{pid}:graveyard", ())), tuple(state.zones.get(f"{pid}:exile", ())),
                     tuple(sorted(state.players[pid].resources.items()))) for pid in state.seat_order)
    field = tuple((cid, c.controller, c.tapped, c.attacking is not None, bool(c.blocking), c.attached_to, c.face_down,
                   tuple(sorted(c.counters.items())))
                  for cid, c in state.cards.items() if c.zone.endswith(":battlefield"))
    log = r.turn_log if r else None  # (conditions read this turn's history: "a creature died this turn")
    history = (log.turn, tuple(log.attacked), tuple(sorted(log.gained.items())), tuple(sorted(log.lost.items())),
               tuple(sorted(log.drew.items())), len(log.left), len(log.left_graveyard),
               len(log.entered_graveyard), len(log.entered)) if log is not None else ()  # (wave 3R1: entered)
    return (state.seq, state.turn.number, state.turn.active_player, players, field,
            r.timestamp if r else 0, len(r.effects) if r else 0, history)


def _conditions(view: Plan, st: Static, tkey: tuple) -> bool:
    """The static's conditions, evaluated once per table state (they never read the affected object)."""
    from app.rules import statics as grammar

    d = st.definition
    if not d.get("conditions"):
        return True
    key = (tkey, st.source, st.controller, repr(d["conditions"]))
    hit = _COND_CACHE.get(key)
    if hit is None:
        if len(_COND_CACHE) > 4096:
            _COND_CACHE.clear()
        hit = _COND_CACHE[key] = grammar.conditions_hold(view, d, source=view.state.cards[st.source], controller=st.controller)
    return hit


def _gate_open(view: Plan, st: Static, tkey: tuple) -> bool:
    """A granted static works while the static granting it applies to the object it's on."""
    if st.gate is None:
        return True
    from app.rules import statics as grammar

    granter, definition = st.gate
    source = view.state.cards.get(granter)
    holder = view.state.cards.get(st.source)
    if source is None or holder is None:
        return False
    gate = Static(granter, source.controller, definition, 0)
    return (grammar.applies(view, definition, source=source, controller=source.controller, card=holder,
                            ch=copiable(view.state, holder, view.info),  # -- copy system (wave 2F): 613.2c --
                            conditions=True) and _conditions(view, gate, tkey))


def _hits(view: Plan, table: list[Static], card: CardInstance, ch: Characteristics, tkey: tuple,
          only_keyword_subjects: bool = False) -> tuple[list[Static], set[str]]:
    """The statics that apply to ``card`` as it is (``ch``) and the rules attached ones impose."""
    from app.rules import statics as grammar

    hits: list[Static] = []
    imposed: set[str] = set()
    for st in table:
        d = st.definition
        source = view.state.cards[st.source]
        if d["static"] == "attached_rule":
            if not only_keyword_subjects and _attached_rule_applies(source, d, card, ch):
                imposed.update(_own(d["imposes"], st.controller))
            continue
        if not _grants(d) or (only_keyword_subjects and not _keyword_subject(d)):
            continue  # (a rules-only static is applied by _with_rules, after layer 7)
        if not _gate_open(view, st, tkey):
            continue
        if not grammar.applies(view, d, source=source, controller=st.controller, card=card, ch=ch, conditions=True):
            continue
        if _conditions(view, st, tkey):
            hits.append(st)
    return hits, imposed


def _layer6(ch: Characteristics, hits: list[Static], effects: list[ContinuousEffect]) -> Characteristics:
    """613.1f in timestamp order (613.7): static keyword grants and resolved effects that add or
    remove keywords interleave — a "loses flying" resolved after a static's source entered beats
    it; a static whose source enters later grants it again."""
    ordered: list[tuple[tuple[int, int, int], Static | ContinuousEffect]] = []
    for st in hits:
        if st.definition["keywords"]:
            ordered.append(((st.seq, 0, 0), st))
    for e in effects:
        if e.layer == "6":
            ordered.append(((e.object_seq, 1, e.timestamp), e))
    ordered.sort(key=lambda x: x[0])
    granted: set[str] = set()
    lost: set[str] = set()
    # (animation, agent A2) "loses all abilities": everything printed and everything granted so
    # far is gone; a static or effect with a later timestamp grants again (613.7). Idempotent:
    # only printed abilities (index < 100) are dropped here; grants are appended after this.
    printed = tuple(a for a in ch.abilities if a.index < 100)
    abilities = printed
    for _, item in ordered:
        if isinstance(item, Static):
            granted |= set(item.definition["keywords"])
            lost -= set(item.definition["keywords"])
        else:
            if item.remove_abilities:
                abilities = ()
                lost |= {k for a in printed if a.kind == "keywords" for k in a.keywords} | granted
                granted = set()
            granted |= set(item.add_keywords)
            granted -= set(item.remove_keywords)
            lost |= set(item.remove_keywords)
            lost -= set(item.add_keywords)
    return replace(ch, granted=frozenset(granted), lost=frozenset(lost), abilities=abilities)


# -- animation (agent A2): layer 4 type changes, layer 5 colors, layer 6 "loses all abilities" ----
_PT_COUNTER = re.compile(r"(?P<p>[+-]\d+)/(?P<t>[+-]\d+)")  # (wave 3R3: a power/toughness counter, 122.1a)

# Subtypes belong to a card type (205.3g-k); when an effect sets the card types (205.1a) the
# subtypes of a type the object no longer has drop with it. Creature types are
# app/rules/creature_types.py's; a subtype in none of the lists below is read as a creature or
# planeswalker type (205.3j) and follows those two types.
LAND_TYPES = frozenset({"Cave", "Desert", "Forest", "Gate", "Island", "Lair", "Locus", "Mine", "Mountain", "Plains",
                        "Planet", "Power-Plant", "Sphere", "Swamp", "Tower", "Town", "Urza\u2019s", "Urza's"})
ARTIFACT_TYPES = frozenset({"Attraction", "Blood", "Bobblehead", "Book", "Clue", "Contraption", "Equipment", "Food",
                            "Fortification", "Gold", "Heartwood", "Incubator", "Infinity", "Junk", "Lander", "Map",
                            "Mutagen", "Powerstone", "Spacecraft", "Stone", "Treasure", "Vehicle", "Vibranium"})
ENCHANTMENT_TYPES = frozenset({"Aura", "Background", "Cartouche", "Case", "Class", "Curse", "Plan", "Role", "Room",
                               "Rune", "Saga", "Shard", "Shrine"})
SPELL_TYPES = frozenset({"Adventure", "Arcane", "Lesson", "Omen", "Trap"})
BATTLE_TYPES = frozenset({"Siege"})


def _subtype_fits(sub: str, types: frozenset[str]) -> bool:
    """Does the object still have a card type this subtype belongs to (205.1a, 205.3d)?"""
    from app.rules.creature_types import CREATURE_TYPES

    if sub in LAND_TYPES:
        return "Land" in types
    if sub in ARTIFACT_TYPES:
        return "Artifact" in types
    if sub in ENCHANTMENT_TYPES:
        return "Enchantment" in types
    if sub in SPELL_TYPES:
        return bool(types & {"Instant", "Sorcery"})
    if sub in BATTLE_TYPES:
        return "Battle" in types
    if sub in CREATURE_TYPES:
        return bool(types & {"Creature", "Kindred", "Tribal"})
    return bool(types & {"Creature", "Kindred", "Tribal", "Planeswalker"})  # (a creature or planeswalker type)


def _layer4(ch: Characteristics, effects: list[ContinuousEffect]) -> Characteristics:
    """613.1d in timestamp order: types set (205.1a: replacing) or added (205.1b: "in addition to
    its other types", "it's still a land", "artifact creature"; a crewed Vehicle, 702.122),
    supertypes gained (205.4b), creature types set (205.1b: the other subtypes stay) or added
    ("becomes a Goblin in addition …", 701.47a), "all creature types"."""
    from app.rules.creature_types import CREATURE_TYPES

    types, subtypes, supers = ch.types, ch.subtypes, ch.supertypes
    for e in effects:  # (``affecting`` sorts by timestamp)
        if e.layer != "4":
            continue
        if e.set_types is not None:
            # (an instant or sorcery keeps that type, 205.1a: never on the battlefield, so moot)
            types = frozenset(e.set_types) | (types & frozenset({"Instant", "Sorcery"}))
        if e.add_types:
            types = types | frozenset(e.add_types)
        if e.add_supertypes:
            supers = supers | frozenset(e.add_supertypes)
        if e.set_creature_types is not None:
            # (a subtype in no list is a creature type — or, on a planeswalker, a planeswalker type, which stays)
            known = LAND_TYPES | ARTIFACT_TYPES | ENCHANTMENT_TYPES | SPELL_TYPES | BATTLE_TYPES
            kept = frozenset(s for s in subtypes if s in known or (s not in CREATURE_TYPES and "Planeswalker" in types))
            subtypes = kept | frozenset(e.set_creature_types)
        if e.all_creature_types:
            subtypes = subtypes | CREATURE_TYPES
        if e.add_subtypes:
            subtypes = subtypes | frozenset(e.add_subtypes)
        subtypes = frozenset(s for s in subtypes if _subtype_fits(s, types))
    if (types, subtypes, supers) == (ch.types, ch.subtypes, ch.supertypes):
        return ch
    return replace(ch, types=types, subtypes=subtypes, supertypes=supers)


def _layer5(ch: Characteristics, effects: list[ContinuousEffect]) -> Characteristics:
    """613.1e in timestamp order: "becomes a green creature" replaces its colors, "colorless"
    removes them, "in addition to its other colors" adds (105.3)."""
    colors = ch.colors
    for e in effects:
        if e.layer != "5":
            continue
        if e.set_colors is not None:
            colors = frozenset(e.set_colors)
        if e.add_colors:
            colors = colors | frozenset(e.add_colors)
    return ch if colors == ch.colors else replace(ch, colors=colors)


def _wipe_key(effects: list[ContinuousEffect]) -> tuple[int, int, int] | None:
    """The ordering key of the latest resolved "loses all abilities" effect on the object (None:
    none): grants ordered before it are gone, later ones apply (613.7)."""
    keys = [(e.object_seq, 1, e.timestamp) for e in effects if e.layer == "6" and e.remove_abilities]
    return max(keys) if keys else None


def _granted_by_effects(ch: Characteristics, effects: list[ContinuousEffect],
                        wipe: tuple[int, int, int] | None) -> Characteristics:
    """Layer 6: quoted abilities resolved effects granted ("gains "{T}: …"", "becomes a … creature
    with "{T}: …""), after the printed (0…99) and static-granted (100…) ones; one that a later
    "loses all abilities" precedes is gone. Each is numbered from its effect's timestamp
    (app/rules/granted.py ``index_of``), so its number doesn't change while other grants end."""
    if not any(e.layer == "6" and e.add_abilities for e in effects):
        return ch
    from app.rules import granted

    return granted.layer6(ch, effects, wipe)


def derive(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None = None) -> Characteristics:
    """Current characteristics: printed + continuous effects in layer order + counters. With
    ``info``, static abilities of permanents apply too (layers 6, 7b, 7c and rules imposed on the
    object it's attached to), and the object's own characteristic-defining P/T (7a, every zone)."""
    global _depth
    # -- copy system (wave 2F): layer 1 — copy effects (613.2a), face-down status (613.2b) --
    from app.rules.copying import layer1

    ch = layer1(state, card, ch, info)
    effects = affecting(state, card)
    each_amounts: dict[int, int] = {}
    ch = _layer4(ch, effects)  # layer 4: type-changing (animation, agent A2: also layer 5 below)
    ch = _layer5(ch, effects)
    imposed = {rule for e in effects for rule in e.imposes}  # "can't block this turn" …
    imposed |= _group_imposed(state, card, ch, info)
    hits: list[Static] = []
    on_field = card.zone.endswith(":battlefield") and state.rules is not None
    if info is not None and on_field and _depth == 0:
        view = _view(state, info)
        table = statics(state, info)
        tkey = _table_key(state) if any(st.definition.get("conditions") or st.gate or st.definition.get("each")
                                        for st in table) else ()
        _depth += 1
        try:
            # a static's subject is read from the object after layer 4 and the resolved layer-6 effects
            hits, rules = _hits(view, table, card, _layer6(ch, [], effects), tkey)
            imposed |= rules
            ch = _layer6(ch, hits, effects)
            if any(_keyword_subject(st.definition) for st in table):
                # 613.8: "creatures with flying …" depends on layer-6 grants of flying: read again with
                # layer 6 applied, until nothing changes (a dependency loop ends in timestamp order)
                for _ in range(3):
                    again, _unused = _hits(view, table, card, ch, tkey, only_keyword_subjects=True)
                    merged = [st for st in hits if not _keyword_subject(st.definition)] + again
                    merged.sort(key=lambda st: st.seq)
                    if merged == hits:
                        break
                    hits = merged
                    ch = _layer6(ch, hits, effects)
            # "… gets +1/+1 for each Elf you control": the count, read now (611.3a), while other
            # objects' characteristics are read without statics (as a condition's are)
            each_amounts = {id(st): _each_amount(view, st, tkey, card) for st in hits if st.definition.get("each")}
        finally:
            _depth -= 1
    elif effects:
        ch = _layer6(ch, [], effects)
    wipe = _wipe_key(effects)  # (animation, agent A2: "loses all abilities" beats earlier grants, 613.7)
    grants = [text for st in hits if wipe is None or (st.seq, 0, 0) > wipe for text in st.definition["grants"]]
    if grants:  # layer 6: granted abilities, numbered after the printed ones (100, 101, …)
        from app.rules.scripts import granted_ability

        extra = []
        for k, text in enumerate(grants):
            ab = granted_ability(text)
            if ab is not None:
                extra.append(replace(ab, index=100 + k))
        ch = replace(ch, abilities=ch.abilities + tuple(extra))
    ch = _granted_by_effects(ch, effects, wipe)
    # layer 7
    setters: list[tuple[tuple[int, int, int], int | None, int | None]] = []
    for st in hits:  # 7b: static "has base power and toughness N/N" (613.4b), by its source's timestamp
        if st.definition.get("base"):
            setters.append(((st.seq, 0, 0), st.definition["base"][0], st.definition["base"][1]))
    for e in effects:  # 7b: resolved setting effects, interleaved by timestamp (613.7)
        if e.layer == "7b":
            setters.append(((e.object_seq, 1, e.timestamp), e.power, e.toughness))
    setters.sort(key=lambda x: x[0])
    power, toughness = _num(ch.power), _num(ch.toughness)
    if info is not None and (power is None or toughness is None):
        cda_p, cda_t = _cda(state, card, ch, info)  # 7a: the object's own characteristic-defining ability (613.4a)
        power = cda_p if cda_p is not None else power
        toughness = cda_t if cda_t is not None else toughness
    if (power is None or toughness is None) and not setters:
        return _with_rules(state, card, ch, info, imposed)  # 7a: a characteristic-defining "*" stays unknown
    p, t = power or 0, toughness or 0
    for _, sp, stt in setters:
        p = sp if sp is not None else p
        t = stt if stt is not None else t
    for st in hits:  # 7c: static modifications (613.4c) …
        p += st.definition["p"]
        t += st.definition["t"]
        each = st.definition.get("each")
        if each is not None:  # "… gets +1/+1 for each Elf you control" (613.4c, a dynamic amount)
            n = each_amounts.get(id(st), 0)
            p += each["p"] * n
            t += each["t"] * n
    p += card.counters.get("+1/+1", 0) - card.counters.get("-1/-1", 0)  # … counters …
    t += card.counters.get("+1/+1", 0) - card.counters.get("-1/-1", 0)
    for kind, n in card.counters.items():  # -- refused copy/mana (wave 3R3) -- other P/T counters ("-0/-1": Wall of Roots)
        m = _PT_COUNTER.fullmatch(kind) if n and kind not in ("+1/+1", "-1/-1") else None
        if m is not None:  # 122.1a / 613.4c: "+X/+Y" counters modify power and toughness
            p += int(m["p"]) * n
            t += int(m["t"]) * n
    for e in effects:  # … and resolved ones
        if e.layer == "7c":
            p += e.power or 0
            t += e.toughness or 0
    for e in effects:
        if e.layer == "7d":
            p, t = t, p
    return _with_rules(state, card, replace(ch, pt=(p, t)), info, imposed)


def _grants(d: dict[str, Any]) -> bool:
    """Does the static change characteristics (layers 6-7)? A rules-only static ("Creatures your
    opponents control can't block.") is applied by ``_with_rules`` instead."""
    return bool(d["p"] or d["t"] or d.get("base") or d["keywords"] or d["grants"] or d.get("each"))


# -- dynamic values (agent F): "for each …" modifications (7c) and characteristic-defining P/T (7a) --
_EACH_CACHE: dict[tuple, int] = {}
_CDA_CACHE: dict[tuple, tuple[int | None, int | None]] = {}
_CDA_VISITING: set[str] = set()


def _static_ctx(view: Plan, source: str, controller: str) -> dict[str, Any]:
    """The context a static's amount is read in: "you" is the source's controller (613), "~" is
    the source (as it is now: it's on the battlefield)."""
    return {"controller": controller, "source_card": source, "source_object": view.oid(source)}


def _each_amount(view: Plan, st: Static, tkey: tuple, card: CardInstance) -> int:
    """The count a "gets +N/+N for each …" static multiplies by, read now (611.3a) and cached per
    table state (``_table_key`` covers everything a value reads). "Other" in the count leaves out
    the affected object (``card``): "Enchanted creature gets +1/+1 for each other creature you
    control", "Each legendary creature you control gets +1/+1 for each other legendary creature"."""
    from app.rules import values

    each = st.definition["each"]
    other = '"other":true' in repr(each["value"])
    key = (tkey, st.source, st.controller, repr(each["value"]), card.id if other else "")
    hit = _EACH_CACHE.get(key) if tkey else None
    if hit is None:
        if len(_EACH_CACHE) > 4096:
            _EACH_CACHE.clear()
        ctx = {**_static_ctx(view, st.source, st.controller), "other_than": card.id}
        hit = values.evaluate(view, ctx, each["value"])
        if tkey:
            _EACH_CACHE[key] = hit
    return hit


def _cda(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo) -> tuple[int | None, int | None]:
    """Layer 7a (613.4a): the object's own characteristic-defining ability that defines its power
    and/or toughness ("~'s power and toughness are each equal to the number of lands you control",
    app/rules/statics.py ``parse_cda``). It functions in every zone (604.3); "you" is its
    controller, or its owner for a card that has none (108.4a). A card played by hand (``manual``
    mode) keeps its printed "*" (unknown). A count that leads back to this object (a loop of CDAs
    reading each other's power) reads it as unknown rather than recursing (613.8: no dependency
    order is modelled beyond that)."""
    r = state.rules
    if r is None or card.id in _CDA_VISITING or r.card_mode(card.id) == "manual":
        return None, None
    from app.rules import scripts, values

    defs = [d for d in scripts.definitions(ch).values() if d.get("static") == "cda"]
    if not defs:
        return None, None
    d = defs[0]
    on_stack_or_field = card.zone == "stack" or card.zone.endswith(":battlefield")
    controller = card.controller if on_stack_or_field else card.owner
    tkey = _table_key(state)
    key = (tkey, card.id, card.zone, controller, repr(d["p"]), repr(d["t"]))
    hit = _CDA_CACHE.get(key)
    if hit is not None:
        return hit
    view = _view(state, info)
    ctx = {"controller": controller, "source_card": card.id, "source_object": r.object_id(card.id)}
    _CDA_VISITING.add(card.id)
    try:
        p = values.evaluate(view, ctx, d["p"]) if d["p"] is not None else None
        t = values.evaluate(view, ctx, d["t"]) if d["t"] is not None else None
    finally:
        _CDA_VISITING.discard(card.id)
    if len(_CDA_CACHE) > 4096:
        _CDA_CACHE.clear()
    _CDA_CACHE[key] = (p, t)
    return p, t


def _with_rules(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None,
                imposed: set[str]) -> Characteristics:
    """Rules imposed on the object (``Characteristics.imposed``): by resolved effects (already in
    ``imposed``), and by static abilities with ``rules`` (app/rules/statics.py: "~ can't be blocked
    by creatures with power 2 or less.", "Islands don't untap during their controllers' untap
    steps.", an Aura's "Enchanted creature … attacks each combat if able."). Statics are read after
    layer 7, so a subject like "creatures with power 4 or greater" sees the current power
    (613.8-style dependency, as far as this engine models it)."""
    global _depth
    if info is not None and card.zone.endswith(":battlefield") and state.rules is not None and _depth == 0:
        from app.rules import statics as grammar

        view = _view(state, info)
        table = [st for st in statics(state, info) if st.definition["static"] == "grant" and st.definition.get("rules")]
        tkey = _table_key(state) if any(st.definition.get("conditions") or st.gate for st in table) else ()
        _depth += 1
        try:
            for st in table:
                d = st.definition
                rules = _own(d["rules"], st.controller)
                if set(rules) <= imposed or not _gate_open(view, st, tkey):
                    continue
                source = state.cards[st.source]
                if grammar.applies(view, d, source=source, controller=st.controller, card=card, ch=ch, conditions=True) \
                        and _conditions(view, st, tkey):
                    imposed.update(rules)
        finally:
            _depth -= 1
    if imposed:
        ch = replace(ch, imposed=ch.imposed | frozenset(imposed))
    return ch


def _own(rules: list[str], controller: str) -> list[str]:
    """-- keyword actions & face-down (wave 3F) -- a rule naming "@you" ("goaded:@you": 701.15b) names the
    static's controller."""
    return [r.replace("@you", controller) for r in rules]


def _keyword_subject(d: dict[str, Any]) -> bool:
    """Does the static's subject ask about keyword abilities ("creatures with flying")?"""
    who = d.get("who") or ""
    return who.startswith("sel:") and ("with_keywords" in who or "without_keywords" in who)


def _attached_rule_applies(source: CardInstance, d: dict[str, Any], card: CardInstance, ch: Characteristics) -> bool:
    """"Enchanted creature can't block.": a rule for the object the source is attached to (303.4b /
    301.5a), while it's the kind of object the ability names."""
    if source.attached_to != card.id:
        return False
    if d.get("permanent"):
        return True
    return ch.is_land if d.get("lands") else ch.is_creature


def _group_imposed(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> set[str]:
    """Rule-modifying effects of resolved spells/abilities on a group ("Creatures can't block this
    turn"): not locked to a set of objects (611.2c), so evaluated now, for whatever matches."""
    r = state.rules
    if r is None or info is None or not r.effects or not card.zone.endswith(":battlefield"):
        return set()
    groups = [e for e in r.effects if e.who is not None]
    if not groups:
        return set()
    from app.rules import selectors

    view = _view(state, info)
    out: set[str] = set()
    for e in groups:
        if e.who is None or set(e.imposes) <= out:
            continue
        src = e.source_card if e.source_card and r.object_id(e.source_card) == e.source else None
        if selectors.matches(view, selectors.from_key(e.who), card, ch, e.controller, src):
            out |= set(e.imposes)
    return out


Layer = Literal["1", "2", "3", "4", "5", "6", "7a", "7b", "7c", "7d"]
Duration = Literal["end_of_turn", "permanent"]


def add_effect(plan: Plan, *, affected: list[str], layer: Layer, source: str | None, controller: str,
               power: int | None = None, toughness: int | None = None, add_keywords: tuple[str, ...] = (),
               remove_keywords: tuple[str, ...] = (), add_types: tuple[str, ...] = (), duration: Duration = "end_of_turn",
               label: str = "", imposes: tuple[str, ...] = (), who: str | None = None,
               source_card: str | None = None, add_subtypes: tuple[str, ...] = (),
               **animation: Any) -> ContinuousEffect:
    """``animation`` (agent A2): the extra ``ContinuousEffect`` fields of a "becomes a …" effect
    (set_types, add_supertypes, set_creature_types, all_creature_types, set_colors, add_colors,
    remove_abilities, add_abilities)."""
    r = plan.rules
    r.timestamp += 1
    effect = ContinuousEffect(id=f"e{r.timestamp}", affected=affected, layer=layer, source=source, controller=controller,
                              power=power, toughness=toughness, add_keywords=list(add_keywords),
                              remove_keywords=list(remove_keywords), add_types=list(add_types),
                              add_subtypes=list(add_subtypes), duration=duration,
                              imposes=list(imposes), who=who, source_card=source_card if who else None,
                              timestamp=r.timestamp, object_seq=r.next_object,
                              label=label[:120], markers=[], **animation)
    r.effects.append(effect)
    return effect


def end_of_turn(plan: Plan) -> None:
    """514.2: "until end of turn" effects end in the cleanup step."""
    r = plan.rules
    r.effects = [e for e in r.effects if e.duration != "end_of_turn"]
    control_sync(plan)  # -- control (wave 3K) -- a Threaten effect ends: the creature goes back (613.1b)


# -- control (wave 3K): layer 2 (613.1b) -----------------------------------------------------------------
# The table keeps a permanent on its controller's side with ``controller`` set; this keeps that in line
# with the control-changing effects: resolved effects ("gain control of target creature until end of
# turn": ``ContinuousEffect.new_controller``, locked to the objects it began with, 611.2c) and the static
# abilities of Auras ("You control enchanted creature."). The latest timestamp wins (613.7); a permanent
# no effect controls any more goes back to its owner, unless a player moved it by hand (only the cards
# an effect moved are in ``RulesState.control_changed``). The object is the same one throughout (no zone
# change: 400.7 doesn't apply), but a new controller restarts "summoning sickness" (302.6: tracked by
# ``controlled_since``), and the permanent leaves combat (506.4: the table action does that).
def control_sync(plan: Plan) -> None:
    """Apply layer 2 to the table, and end "for as long as …" effects it makes untrue (611.2b),
    until nothing changes."""
    r = plan.rules
    if r is None or not (r.effects or r.control_changed or any(c.attached_to for c in plan.state.cards.values())):
        return
    from app.rules import delayed

    for _ in range(8):
        delayed.expire(plan)
        if not _control_pass(plan):
            return


def _control_pass(plan: Plan) -> bool:
    from app.rules import scripts

    state, r = plan.state, plan.rules
    battle = {cid: c for cid, c in state.cards.items() if c.zone.endswith(":battlefield")}
    live = set(plan.live())
    entries: dict[str, list[tuple[tuple[int, int, int], str]]] = {}
    by_object = {plan.oid(c): cid for cid, c in battle.items()} if any(e.layer == "2" for e in r.effects) else {}
    for e in r.effects:
        if e.layer == "2" and e.new_controller:
            for oid in e.affected:
                if oid in by_object:
                    entries.setdefault(by_object[oid], []).append(((e.object_seq, 1, e.timestamp), e.new_controller))
    for cid, c in battle.items():  # "You control enchanted creature." (a static: whatever it is attached to now, 611.3a)
        if c.attached_to in battle and not c.face_down and c.controller in live and any(
                d.get("static") == "control" for d in scripts.definitions(copiable(state, c, plan.info)).values()):
            entries.setdefault(c.attached_to, []).append(((timestamp(state, cid), 0, 0), c.controller))
    changed = False
    for cid in sorted(set(entries) | set(r.control_changed)):
        card = battle.get(cid)
        if card is None:
            r.control_changed = [x for x in r.control_changed if x != cid]
            continue
        valid = [p for _, p in sorted(entries.get(cid, ())) if p in live]  # (800.4a: a departed player's effects ended)
        if valid:
            want: str | None = valid[-1]
            if cid not in r.control_changed and want != card.controller:
                r.control_changed.append(cid)
        elif cid in r.control_changed:
            want = card.owner if card.owner in live else None
            r.control_changed.remove(cid)
        else:
            continue
        if want is not None and want != card.controller:
            plan.do({"type": "set_controller", "card_ids": [cid], "player": want}, actor=want)
            changed = True
    return changed


def prune(state: GameState) -> None:
    """Drop effects none of whose objects still exist (bookkeeping only; they couldn't apply)."""
    r = state.rules
    if r is None or not r.effects:
        return
    live = {r.object_id(cid) for cid, c in state.cards.items() if c.zone.endswith(":battlefield")}
    r.effects = [e for e in r.effects if e.who is not None or set(e.affected) & live]
