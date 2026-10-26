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
Group statics of layers 4-6 (app/rules/group_layers.py, wave 22A) are solved against each other: 613.6 (the objects an effect began with), 613.8 (dependencies, loops in timestamp order), 305.7. Otherwise: a static's subject is read from the object after layer 4 and the resolved
layer-6 effects; a subject that asks about keywords ("creatures with flying …") is read again once
layer 6 is applied, until nothing changes — other dependencies (types, power) aren't modelled.
Layers 1–5 (copy, control, text, color) are next; the model already carries the layer number.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from app.game.rules_state import ContinuousEffect
from app.game.state import CardInstance, GameState
from app.rules import chosen as _chosen  # -- chosen filters (wave 53B) --
from app.rules import read_pass
from app.rules.characteristics import AbilityText, CardInfo, Characteristics
from app.rules.world_durations80 import native as world_native80

if TYPE_CHECKING:
    from app.rules.plan import Plan


def _num(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def spell_entry(state: GameState, card: CardInstance, info: CardInfo | None) -> bool:
    """400.7a: live effects on a native permanent spell follow its battlefield entry."""
    if info is None or state.rules is None or not card.zone.endswith(':battlefield'):
        return False
    original = state.cards.get(card.id)
    entry = state.rules.stack.get(card.id)
    return bool(original is not None and original.zone == 'stack' and original.ability is None
                and (entry is None or entry.kind == 'spell') and copiable(state, original, info).is_permanent_card)


def affecting(state: GameState, card: CardInstance, info: CardInfo | None = None) -> list[ContinuousEffect]:
    new_object = False
    probe = _T.probe
    if probe is not None and (state is probe.origin or state is probe.state) and card.id == probe.incoming.id:
        state = probe.origin
        original = state.cards.get(card.id)
        new_object = (original is None or not original.zone.endswith(":battlefield")) and not spell_entry(state, card, info)
    r = state.rules
    # (-- color lace (wave 46B) -- a spell on the stack is affected too: "Target spell or permanent becomes blue" locks in the spell, 611.2c)
    if r is None:
        return []
    if not (card.zone.endswith(":battlefield") or card.zone == "stack"):
        zone = card.zone.rsplit(':', 1)[-1]
        if zone not in ('exile', 'graveyard'):
            return []
        oid = r.object_id(card.id)
        # An explicit outside-zone grant changes only the object's actual abilities.
        return sorted([ContinuousEffect(id=e.id, affected=[oid], layer='6', source=e.source,
                                        controller=e.controller, timestamp=e.timestamp, object_seq=e.object_seq,
                                        add_abilities=e.add_abilities, duration=e.duration, label=e.label,
                                        ability_zone=zone)
                       for e in r.effects if e.ability_zone == zone and e.layer == '6'
                       and e.add_abilities and oid in e.affected and e.declaration_window is None],
                      key=lambda e: e.timestamp)
    oid = r.object_id(card.id)
    from app.rules import entry_characteristics, keyword_denials

    effects = entry_characteristics.effects(state, card)
    for effect in r.effects:
        if new_object:
            continue  # Native entry forms above apply; earlier incarnations do not.
        if effect.ability_zone is not None or effect.declaration_window is not None or oid not in effect.affected:
            continue
        if prohibited := effect.blocked_keywords.get(oid):
            keywords, abilities = keyword_denials.filter_grants(effect.add_keywords, effect.add_abilities, set(prohibited))
            effect = effect.model_copy(update={"add_keywords": keywords, "add_abilities": abilities})
        effects.append(effect)
    return sorted(effects, key=lambda e: e.timestamp)


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
    # -- layers (wave 22A) -- 613.6: a layered group static ("layered" in its definition: app/rules/group_layers.py) applies to the
    # objects it began applying to, in every layer; the objects (card ids) found when the table was solved. None: not solved.
    members: frozenset[str] | None = None
    order: float = 0  # the timestamp its layer 4-5 parts are applied at: its own, or just after what it depends on (613.8b)
    effect_key: tuple[int, int, int] | None = None  # resolved ability grant's original timestamp
    ability_index: int | None = field(default=None, compare=False)  # Exact source definition item, never rendered holder position.
    ability_path: tuple[int, ...] = field(default=(), compare=False)

    @property
    def key(self) -> tuple[int, int, int]:
        return self.effect_key or (self.seq, 0, 0)



STATIC_GRANT_CAPTURE45 = True


class _Derivation(threading.local):
    """-- review (wave 29A) -- Where this thread's derivation is (re-entrancy): per thread, as two games, or two viewers of one game, are
    derived at once (GET /view runs on the server's threadpool while actions run on the event loop). Shared by the process, one thread's
    derivation part-way made another's skip every static ability (``depth``) or read the other table's statics (``solving``)."""

    def __init__(self) -> None:
        self.grant_capture45: Any = None
        self.borrow_capture: dict[str, list[Static]] | None = None
        self.borrow_graph: Any = None
        self.probe: Any = None  # one transient prospective field, never cached
        self.depth = 0  # a static's subject or condition reading another object's characteristics
        self.memo: list[Any] | None = None  # (wave 5R) [state, info, table]: the statics table one top-level ``derive`` reads
        self.solving: list[list[Static]] = []  # (wave 22A) the table being solved: group_layers.solve
        self.l4: set[str] = set()  # (wave 4B) the objects whose own layer-4/5 statics' conditions are being read
        self.cda: set[str] = set()  # the objects whose characteristic-defining P/T is being read
        self.pt: dict[str, tuple[int, int] | None] = {}  # (wave 42A) the object whose rule static is being judged -> its power / toughness after layer 7


_T = _Derivation()
_STATIC_CACHE: dict[tuple, tuple[list[Static], dict[str, tuple[int, int, int]], bool, dict[tuple, list[Static]], list[tuple[str, str]]]] = {}


def timestamp(state: GameState, card_id: str) -> int:
    """A permanent's timestamp: the object number it got as it entered (613.7d), or the later one
    it received since — as an Aura, Equipment or Fortification that became attached (613.7e), as
    it turned face up or down (613.7f) or as a double-faced permanent that transformed (613.7g;
    ``RulesState.restamped``)."""
    r = state.rules
    if r is None:
        return 0
    probe = _T.probe
    if probe is not None and (state is probe.origin or state is probe.state) and probe.incoming.id == card_id:
        original = probe.origin.cards.get(card_id)
        if original is None or not original.zone.endswith(":battlefield"):
            return r.next_object + 1
    return max(r.objects.get(card_id, 0), r.restamped.get(card_id, 0))


def statics(state: GameState, info: CardInfo) -> list[Static]:
    """Static grants and attached rules of permanents on the battlefield, read from printed
    abilities and from abilities other statics grant; cached by what is on the battlefield, in
    timestamp order. Whether each applies to a given object, and its conditions, are evaluated
    by ``derive``."""
    probe = _T.probe
    if probe is not None and (state is probe.origin or state is probe.state):
        return probe.table
    if _T.solving:  # -- layers (wave 22A) -- a condition read while the layered statics are being solved: the table as it is so far
        return _T.solving[-1]
    memo = _T.memo  # -- review (wave 5R) -- one derive reads the table up to four times: its key once
    if memo is not None and memo[0] is state and memo[1] is info and memo[2] is not None:
        return memo[2]
    r = state.rules
    live = {p for p in state.seat_order if not state.players[p].left} - (set(r.conceded) | set(r.lost) if r else set())
    # -- copy system (wave 2F): statics are read from copiable values (613.2c: a Clone of an anthem
    # has the anthem's ability), so which copy effect applies to each permanent is part of the key
    from app.rules.copying import copy_index

    copies = copy_index(r)
    # (the face and flip state are part of the key: a transformed permanent has only its back
    # face's characteristics, 712.8e — its front face's statics are gone, 611.3a)
    key = tuple(sorted((cid, c.controller, c.face_down, c.face, c.flipped, c.card_id or c.name, c.token.text if c.token else "",
                        r.card_mode(cid) if r else "", timestamp(state, cid), tuple(sorted(c.choices.items())), tuple(p.model_dump_json() for p in c.stickers101),  # (wave 33B: linked words, 607.2f; wave 53B: and what else it chose as it entered, 614.12a: a type or a color written into its statics)
                        copies.get(r.object_id(cid), (0, "")) if r else (0, ""))
                       for cid, c in state.cards.items() if c.zone.endswith(":battlefield")))
    # -- conditional statics (wave 4B) -- statics that function from a graveyard (113.6b): which cards are there
    graveyards = tuple((p, tuple(state.zones.get(f"{p}:graveyard", ()))) for p in state.seat_order)
    # -- review (Codex) -- also read below: graveyard cards' automation modes and what each permanent is attached to
    # (a "loses all abilities" Aura's host, attached_types.wipes)
    gy_modes = tuple(r.card_mode(cid) for _, ids in graveyards for cid in ids) if r else ()
    hosts = tuple(sorted((cid, c.attached_to or "") for cid, c in state.cards.items()
                         if c.zone.endswith(":battlefield") and c.attached_to))
    # -- emblems (wave 13A) -- 114: the emblems in the command zones (their text is part of the key)
    emblems = tuple(sorted((cid, c.owner, c.token.text) for cid, c in state.cards.items()
                           if c.token is not None and c.zone.endswith(":command") and c.token.type_line == "Emblem"))
    impending = tuple(sorted(cid for cid, c in state.cards.items()
                             if r is not None and c.zone.endswith(":battlefield")
                             and (record := r.payments.get(r.object_id(cid))) is not None
                             and record.alternative == "impending"))
    text71 = tuple((e.id, tuple(e.affected), e.set_name,
                    (e.text_change71.category, e.text_change71.old, e.text_change71.new) if e.text_change71 is not None else None)
                   for e in r.effects if e.layer == '3') if r else ()
    key_all: tuple = (key, graveyards, gy_modes, hosts, emblems, tuple(sorted(live)), impending, text71,
                      tuple((oid, tuple((v.card, v.acquisition, v.word) for v in entries)) for oid, entries in sorted(r.color_words71.items())) if r else (),
                      # -- attached events (wave 4L) -- "loses all abilities" effects: their objects' statics are gone
                      tuple(e.id for e in r.effects if e.remove_abilities or e.set_land_types is not None) if r else (),
                      # -- layers (wave 22A) -- the resolved effects the group layers (4-6) are solved against (613.6, 613.8)
                      tuple((e.id, tuple(e.affected)) for e in r.effects if e.layer in ("4", "5", "6")) if r else (),
                      tuple(sorted(r.levels.items())) if r else (),  # -- Class (wave 16A) -- 716.2a: the levels reached
                      tuple(sorted((o, tuple(d)) for o, d in r.unlocked.items())) if r else ())  # -- Rooms (wave 18G) -- the doors unlocked
    hit = _STATIC_CACHE.get(key_all)
    if hit is not None:
        # -- layers (wave 22A) -- the layered group statics are solved against the table state (their conditions are read now)
        tkey = _table_key(state) if hit[2] else ()
        table = hit[3].get(tkey)
        if table is None:
            if len(hit[3]) > 8:
                hit[3].clear()
            table = hit[3][tkey] = _finish(state, info, hit[0], hit[1], hit[4], tkey)
        if memo is not None and memo[0] is state and memo[1] is info:
            memo[2] = table
        return table
    from app.rules import scripts
    from app.rules import statics as grammar

    field = [(cid, c) for cid, c in state.cards.items()
             if c.zone.endswith(":battlefield") and not c.face_down and c.controller in live and c.owner in live
             and not (r is not None and r.card_mode(cid) == "manual")]
    out = []
    for cid, c in field:
        for ability_index, d in scripts.definitions(source_text71(state, c, copiable(state, c, info), info)).items():
            if d["kind"] == "static" and d.get("static") in ("grant", "attached_rule") and not grammar.zone_static(d):
                if (d := _chosen.resolve_marks(d, c)) is None:  # type: ignore[assignment]  # (wave 53B: the type or color it chose; none recorded: nothing to apply)
                    continue
                out.append(Static(cid, c.controller, d, timestamp(state, cid), ability_index=ability_index))
                # -- as long as (wave 9B) -- the other sentences of one ability (static_pairs.py): statics of the same permanent
                out += [Static(cid, c.controller, extra, timestamp(state, cid), ability_index=ability_index, ability_path=(part,))
                        for part, extra in enumerate(d.get("also", ()))]
            elif d.get('kind') == 'static' and d.get('static') == 'replace' and 'also' in d:
                from app.rules import conditional_prevention_grants45

                if (extra := conditional_prevention_grants45.layer6_grant(d)) is not None:
                    out.append(Static(cid, c.controller, extra, timestamp(state, cid), ability_index=ability_index, ability_path=(0,)))
    out += _resolved_mana_statics(state, [(cid, card.controller) for cid, card in field])
    # -- conditional statics (wave 4B) -- "As long as this card is in your graveyard and you control a Mountain,
    # creatures you control have haste." (Anger): an ability that states the zone it functions in functions only
    # from there (113.6b); "you" is its owner (108.4a). Its timestamp: the object number it got as it went there.
    for p, ids in graveyards:
        if p not in live:
            continue
        for cid in ids:
            c = state.cards[cid]
            if c.owner != p or c.face_down or (r is not None and r.card_mode(cid) == "manual"):
                continue
            printed = copiable(state, c, info)
            if "in your graveyard" not in printed.oracle_text:
                continue
            for ability_index, d in scripts.definitions(printed).items():
                if d["kind"] == "static" and d.get("static") == "grant" and grammar.zone_static(d):
                    out.append(Static(cid, p, d, timestamp(state, cid), ability_index=ability_index))
    # -- emblems (wave 13A) -- 114.4: an emblem's static abilities apply as long as it exists; its owner controls it (114.3)
    for cid, owner, _ in emblems:
        if owner in live:
            out += [Static(cid, owner, d, timestamp(state, cid), ability_index=ability_index)
                    for ability_index, d in scripts.definitions(copiable(state, state.cards[cid], info)).items()
                    if d["kind"] == "static" and d.get("static") == "grant"]
    # -- attached events (wave 4L) -- a permanent that lost all abilities (613.1f: by a resolved effect, or by an
    # Aura's "Enchanted creature loses all abilities") has none of its static abilities: they don't apply
    # Keep source definitions raw: 305.7 and layer6 source loss are solved at
    # their actual layer, after earlier-start effects lock their members (613.6).
    wiped: dict[str, tuple[int, int, int]] = {}
    if len(_STATIC_CACHE) > 256:
        _STATIC_CACHE.clear()
    from app.rules.layer_dependency_graph import has_layer4

    # Impending contributes synthetic layer-4 nodes even without a parsed group
    # static. Their counter-dependent results need the dynamic table cache key.
    layered = bool(impending) or any(st.definition.get("layered") or has_layer4(st.definition) or st.definition.get("lose_all")
                  or "set_colors" in st.definition or "add_colors" in st.definition for st in out)
    heads = [(cid, c.controller) for cid, c in field]
    hit = _STATIC_CACHE[key_all] = (out, wiped, layered, {}, heads)
    tkey = _table_key(state) if layered else ()
    table = hit[3][tkey] = _finish(state, info, out, wiped, heads, tkey)
    if memo is not None and memo[0] is state and memo[1] is info:
        memo[2] = table
    return table


def _finish(state: GameState, info: CardInfo, out: list[Static], wiped: dict[str, tuple[int, int, int]],
            field: list[tuple[str, str]], tkey: tuple) -> list[Static]:
    """The statics table: the layered group statics solved (613.6, 613.8: app/rules/group_layers.py), then the statics other
    statics grant, in timestamp order."""
    # -- layers (wave 22A) -- statics of permanents that lost all abilities to a group static are gone too; a static that
    # applies to some objects keeps the objects it began applying to (613.6)
    from app.rules import group_layers
    from app.rules.layer_dependency_graph import StaticTable

    out, lost = group_layers.solve(state, info, out, tkey)
    out = out.detached() if isinstance(out, StaticTable) else list(out)
    wiped = {cid: max(wiped.get(cid, k), lost.get(cid, k)) for cid, k in {**wiped, **lost}.items()}
    return _extend_statics(state, info, out, wiped, field)


def _extend_statics(state: GameState, info: CardInfo, out: list[Static], wiped: dict[str, tuple[int, int, int]],
                    field: list[tuple[str, str]]) -> list[Static]:
    """Existing granted-static discovery, shared with the prospective field."""
    from app.rules import damage_retention83, scripts
    from app.rules import statics as grammar

    # An ability a static grants may itself be a static ("Commander creatures you own have
    # "Creature tokens you control get +2/+2.""): it works on whatever it's granted to, with the
    # later of the two timestamps (613.7a), while the granting static applies to that object.
    for st in list(out):
        if st.definition["static"] != "grant":
            continue
        for text in st.definition.get("grants", ()):
            # (wave 42A) 702.98a: a granted "Unleash" brings its second half, the static "can't block as long as it has a +1/+1 counter" (the first, the counter, is
            # chosen as it enters: riot.py); the same static the printed keyword is (scripts.define)
            inner = grammar.parse("~ can't block as long as it has a +1/+1 counter on it." if text.rstrip(".").lower() == "unleash" else scripts.self_text(text, ""))
            if inner is None:
                continue
            for cid, controller in field:
                seq = max(st.seq, timestamp(state, cid))
                if cid in wiped and (seq, 0, 0) <= wiped[cid]:
                    continue  # -- attached events (wave 4L) -- granted before it lost all abilities (613.7)
                out.append(Static(cid, controller, inner, seq, gate=(st.source, st.definition)))
    # Resolved quoted self statics use the granting effect's exact timestamp.
    # Limit discovery to native layer-6 keyword/rule statics; introducing layer-4
    # dependencies here would require solving those grants as dependency nodes.
    if state.rules is not None:
        from app.rules import stickers101

        sticker_effects101 = [e for cid, _controller in field for e in stickers101.continuous(state, state.cards[cid])]
        for effect in [*state.rules.effects, *sticker_effects101]:
            if effect.layer != "6" or not effect.add_abilities:
                continue
            key = (effect.object_seq, 1, effect.timestamp)
            for cid, controller in field:
                if state.rules.object_id(cid) not in effect.affected or (cid in wiped and key <= wiped[cid]):
                    continue
                for text in effect.add_abilities:
                    inner = grammar.parse(scripts.self_text(text, ""))
                    if effect.id.startswith('sticker101:') and inner is not None and inner.get('who') == 'self':
                        source_effects = affecting(state, state.cards[cid], info)
                        if any(e.layer == '6' and e.remove_abilities and (e.object_seq, 1, e.timestamp) > key for e in source_effects):
                            continue
                        # The canonical sticker static grants are layer6/7 only;
                        # no type-changing dependency node is introduced here.
                        if not inner.get('layer4') and not inner.get('base'):
                            out.append(Static(cid, controller, inner, effect.object_seq, effect_key=key))
                        continue
                    if inner is None or (inner.get("who") != "self" and not damage_retention83.resolved_static(inner)) or inner.get("layer4") or inner.get("base") or inner.get("p") or inner.get("t") or inner.get("grants"):
                        continue
                    if inner.get("keywords") or inner.get("rules") or inner.get("each"):  # (each: "gets +1/+1 for each ..." granted by a resolved effect, 613.4c; wave 110D)
                        out.append(Static(cid, controller, inner, effect.object_seq, effect_key=key))
    out.sort(key=lambda st: st.key)
    return out


def _resolved_mana_statics(state: GameState, field: list[tuple[str, str]]) -> list[Static]:
    """Native layer-6-only gained mana grants, retained as raw source nodes."""
    from app.rules import mana as M
    from app.rules import scripts
    from app.rules import statics as grammar

    if state.rules is None:
        return []
    out = []
    for effect in state.rules.effects:
        if effect.layer != '6' or not effect.add_abilities:
            continue
        key = (effect.object_seq, 1, effect.timestamp)
        for cid, controller in field:
            card = state.cards.get(cid)
            if card is None or not card.zone.endswith(':battlefield') or state.rules.object_id(cid) not in effect.affected:
                continue
            for text in effect.add_abilities:
                inner = grammar.parse(scripts.self_text(text, ''))
                if inner is None or inner.get('static') != 'grant' or not inner.get('grants'):
                    continue
                if any(k in inner for k in ('layer4', 'set_colors', 'add_colors', 'set_name', 'chosen_color')) or any(
                        inner.get(k) for k in ('p', 't', 'base', 'base_mv', 'keywords', 'rules', 'lose_all', 'also')):
                    continue
                if all(M.parse_mana_ability(ability) is not None for ability in inner['grants']):
                    out.append(Static(cid, controller, inner, effect.object_seq, effect_key=key))
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

    probe = _T.probe
    if probe is not None and (state is probe.origin or state is probe.state):
        state = probe.state
    view = Plan.__new__(Plan)
    view.state, view.info = state, info
    return view


_COND_CACHE: dict[tuple, bool] = {}


def _table_key(state: GameState) -> tuple:
    """Everything a static's condition or dynamic amount ("for each …", a CDA's count) may read
    (611.3a: checked whenever it's looked at), so one verdict per static serves a whole pass over
    the table: life, hands, graveyards and exile (which cards: "creature cards in your graveyard"),
    players' counters, the permanents with their status and counters, and the resolved effects."""
    probe = _T.probe
    prospective = probe is not None and (state is probe.origin or state is probe.state)
    if prospective:
        state = probe.state
    r = state.rules
    players = tuple((pid, state.players[pid].life, len(state.zones.get(f"{pid}:hand", ())),
                     tuple(state.zones.get(f"{pid}:graveyard", ())), tuple(state.zones.get(f"{pid}:exile", ())),
                     tuple(sorted(state.players[pid].resources.items()))) for pid in state.seat_order)
    field = tuple((cid, c.controller, c.tapped, c.is_attacking, c.is_blocking, c.attached_to, c.face_down,
                   tuple(sorted(c.counters.items())), c.face, c.blocking, tuple(c.blocking_more),  # (wave 35D: face, whom it blocks)
                   tuple(sorted(c.choices.items())))  # (wave 53B: what it chose as it entered, 614.12a: recorded after it is on the battlefield, a count reading it must not be served from before)
                  for cid, c in state.cards.items() if c.zone.endswith(":battlefield"))
    log = r.turn_log if r else None  # (conditions read this turn's history: "a creature died this turn")
    history = (log.turn, tuple(log.attacked), tuple(sorted(log.gained.items())), tuple(sorted(log.lost.items())),
               tuple(sorted(log.drew.items())), len(log.left), len(log.left_graveyard),
               len(log.entered_graveyard), len(log.entered),  # (wave 3R1: entered)
               # -- this-turn history (wave 4D) -- spells cast, facts, attackers, lands played
               len(log.casts), len(log.facts), tuple(sorted((p, len(a)) for p, a in log.attackers.items())),
               len(r.events), r.trigger_batch,  # (wave 24A: facts of events not yet looked at are read too, history.log_for)
               tuple(sorted((p, (c.turn, c.count)) for p, c in r.lands_played.items()))) if log is not None and r else ()
    designations = (tuple(r.monstrous), tuple(r.renowned), tuple(r.suspected),  # -- conditional statics (wave 4B) --
                    # -- as long as (wave 35D) -- what a static's condition reads of an object's past, the Ring-bearer, the unlocked doors
                    tuple(r.dealt_damage), tuple(sorted(r.ring_bearers.items())), tuple(r.payments), tuple(sorted(r.devoured.items())),  # (wave 48B: "if it devoured a creature")
                    tuple(sorted((k, tuple(v)) for k, v in r.unlocked.items()))) if r else ()
    key = (state.seq, state.turn.number, state.turn.active_player, players, field,
           r.timestamp if r else 0, len(r.effects) if r else 0, history, designations)
    return (*key, probe.incoming.model_dump_json()) if prospective else key


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


def probing(state: GameState, card: CardInstance) -> bool:
    """-- review (wave 22A) -- Is ``card`` the object as it would exist on the battlefield (614.12: entering, or under another
    controller), not the permanent the statics table was solved with? Then a layered group static's subject is read from it."""
    probe = _T.probe
    if probe is not None and (state is probe.origin or state is probe.state) and card.id == probe.incoming.id:
        return False  # The shared graph already solved this prospective exact object.
    real = state.cards.get(card.id)
    return real is None or real.zone != card.zone or real.controller != card.controller


def _hits(view: Plan, table: list[Static], card: CardInstance, ch: Characteristics, tkey: tuple,
          only_keyword_subjects: bool = False) -> tuple[list[Static], set[str]]:
    """The statics that apply to ``card`` as it is (``ch``) and the rules attached ones impose."""
    from app.rules import statics as grammar

    hits: list[Static] = []
    imposed: set[str] = set()
    for index, st in enumerate(table):
        d = st.definition
        source = view.state.cards[st.source]
        if d["static"] == "attached_rule":
            if not only_keyword_subjects and _attached_rule_applies(source, d, card, ch):
                from app.rules import attack_requirements

                rules = _own(d["imposes"], st.controller, card.owner)
                imposed.update(rules)
                imposed.update(attack_requirements.instances(rules, f"static:{st.source}:{st.seq}:{index}"))
            continue
        if not _grants(d) or (only_keyword_subjects and not _keyword_subject(d)):
            continue  # (a rules-only static is applied by _with_rules, after layer 7)
        if not _gate_open(view, st, tkey):
            continue
        solved = st.members is not None and not probing(view.state, card)
        if solved:  # -- layers (wave 22A) -- 613.6: the objects it began applying to
            if card.id not in (st.members or ()):
                continue
        elif not grammar.applies(view, d, source=source, controller=st.controller, card=card, ch=ch, conditions=True):
            continue
        if solved or _conditions(view, st, tkey):  # (a solved static's conditions were read as it was solved)
            if d.get("chosen_keywords"):  # -- commander sweep (wave 49B) -- "have each of the chosen abilities" (Greymond): the pair its permanent chose as it entered (614.12a), read now (the table is cached)
                st = replace(st, definition={**d, "keywords": (source.choices.get("Chosen abilities") or "").split(" and ") if source.choices.get("Chosen abilities") else []})
            hits.append(st)
    return hits, imposed


# -- counters (wave 5H) --
def keyword_counters(state: GameState, card: CardInstance) -> list[tuple[tuple[int, int, int], str]]:
    """122.1b, 613.1f: keyword counters grant abilities in every zone, including retained counters
    on cards outside the battlefield (Skullbriar). Each has its layer-6 ordering key
    (613.7c: the timestamp the newest counter of that kind got, ``RulesState.counter_stamps``; a counter it was
    created with has the permanent's own timestamp)."""
    from app.game.rules_state import KEYWORD_COUNTERS

    if not card.counters:
        return []
    stamps = state.rules.counter_stamps.get(card.id, {}) if state.rules is not None else {}
    out: list[tuple[tuple[int, int, int], str]] = []
    for kind, n in sorted(card.counters.items()):
        if n > 0 and kind in KEYWORD_COUNTERS:
            stamp = stamps.get(kind)
            key = (stamp[0], 1, stamp[1]) if stamp else (timestamp(state, card.id), 0, 0)
            # CR 122.1b, 613.7c: each counter grants an instance; all counters of
            # this kind share the latest timestamp. Multiple exalted instances matter.
            out.extend((key, kind) for _ in range(n if kind in ("exalted", "decayed") else 1))
    return out
# -- end counters (wave 5H) --


def _flanking_instances(texts: tuple[str, ...]) -> int:
    from app.rules.oracle import parse_abilities

    return sum(ability.keywords.count("flanking") for text in texts for ability in parse_abilities(text)
               if ability.kind == "keywords")


def _layer6(ch: Characteristics, hits: list[Static], effects: list[ContinuousEffect],
            counters: list[tuple[tuple[int, int, int], str]] | None = None) -> Characteristics:
    """613.1f in timestamp order (613.7): static keyword grants and resolved effects that add or
    remove keywords interleave — a "loses flying" resolved after a static's source entered beats
    it; a static whose source enters later grants it again. (wave 5H) ``counters``: keyword counters (122.1b)."""
    from app.rules import banding, keyword_denials

    # Parameterized banding keywords must participate at their grant's timestamp,
    # even when the abilities themselves are appended after this layer pass.
    static_bands = {id(st): frozenset(k for text in st.definition.get("grants", ())
                                     for k in banding.parameter_keywords(text)) for st in hits}
    effect_bands = {e.id: frozenset(k for text in e.add_abilities for k in banding.parameter_keywords(text)) for e in effects if e.layer == "6"}
    band_keys = {k for a in ch.abilities for k in a.keywords if banding.quality(k) is not None}
    band_keys |= {k for ks in static_bands.values() for k in ks} | {k for ks in effect_bands.values() for k in ks}
    band_keys |= {k for e in effects for k in e.add_keywords if banding.quality(k) is not None}

    def removed(keys: Any) -> set[str]:
        gone = set(keys)
        if "hexproof" in gone:
            gone.add("hexproof from")
        if "banding" in gone:  # CR 702.22b: losing banding also loses all its qualified forms.
            gone.add(banding.OTHER)
        return gone | band_keys if banding.OTHER in gone else gone

    static_flanks = {id(st): _flanking_instances(tuple(st.definition.get("grants", ())))
                     + st.definition["keywords"].count("flanking") for st in hits}
    effect_flanks = {e.id: _flanking_instances(tuple(e.add_abilities)) + e.add_keywords.count("flanking")
                     for e in effects if e.layer == "6"}
    ordered: list[tuple[tuple[int, int, int], Static | ContinuousEffect | str]] = []
    ordered += [(key, "kw:" + kw) for key, kw in counters or ()]  # -- counters (wave 5H) --
    for st in hits:
        bands, flanks = static_bands[id(st)], static_flanks[id(st)]
        if bands or flanks:
            st = replace(st, definition={**st.definition, "keywords": [*st.definition["keywords"], *sorted(bands),
                                                                     *(["flanking"] if flanks else [])],
                                         "flanking_instances": flanks})
        if st.definition["keywords"] or st.definition.get("lose_keywords"):
            ordered.append((st.key, st))
        if st.definition.get("lose_all"):  # -- attached events (wave 4L) -- "Enchanted creature loses all abilities"
            from app.rules.attached_types import wipe_key

            ordered.append((wipe_key(st), "wipe-mana" if st.definition.get("keep_mana") else "wipe"))
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
    flanking_count = sum(a.keywords.count("flanking") for a in printed if a.kind == "keywords")
    for _, item in ordered:
        if item in ("wipe", "wipe-mana"):  # -- attached events (wave 4L) -- a static "loses all abilities" (613.1f, 613.7)
            abilities = tuple(a for a in abilities if a.kind == "mana") if item == "wipe-mana" else ()  # (wave 22A: "except mana abilities", Blood Sun)
            lost |= {k for a in printed if a.kind == "keywords" for k in a.keywords} | granted
            granted = set()
            flanking_count = 0
        elif isinstance(item, str) and item.startswith("kw:"):  # -- counters (wave 5H) -- a keyword counter
            granted.add(item[3:])
            lost.discard(item[3:])
            if item[3:] == "flanking":
                flanking_count += 1
            if item[3:] in ("exalted", "decayed"):
                # Full keyword abilities, so the existing trigger machinery reads
                # each instance and timestamp-ordered ability loss removes it.
                abilities += (AbilityText(index=20_000 + len(abilities), text=item[3:].capitalize(),
                                          kind="keywords", keywords=(item[3:],)),)
        elif isinstance(item, Static):
            flanking_count += item.definition.get("flanking_instances", item.definition["keywords"].count("flanking"))
            granted |= set(item.definition["keywords"])
            lost -= set(item.definition["keywords"])
            gone = removed(item.definition.get("lose_keywords") or ())  # -- attached events (wave 4L) -- "loses flying"
            if "flanking" in gone:
                flanking_count = 0
            lost |= gone
            granted -= gone
        elif isinstance(item, ContinuousEffect):
            if item.lose_quoted_ability is not None:
                from app.rules import quoted_prevention_loss47

                abilities = tuple(a for a in abilities if not quoted_prevention_loss47.matches(a.text, ch.name))
            if item.lose_index:  # -- licids (wave 50A) -- 613.1f: "This creature loses this ability" (only that printed one)
                abilities = tuple(a for a in abilities if a.index not in item.lose_index)
            if item.remove_abilities:
                flanking_count = 0
                abilities = ()
                lost |= {k for a in printed if a.kind == "keywords" for k in a.keywords} | granted
                granted = set()
            added = set(item.add_keywords) | set(effect_bands.get(item.id, ()))
            if effect_flanks.get(item.id):
                added.add("flanking")
            gone = removed(item.remove_keywords)
            if "flanking" in gone:
                flanking_count = 0
            flanking_count += effect_flanks.get(item.id, 0)
            granted |= added
            granted -= gone
            lost |= gone
            lost -= added
    prohibited = {rule[len(keyword_denials.PREFIX):] for e in effects for rule in e.imposes
                  if rule.startswith(keyword_denials.PREFIX)}
    for st in hits:  # A prohibition overrides later grants, regardless of timestamps.
        prohibited.update(st.definition.get("deny_keywords") or ())
    deny = removed(prohibited)
    granted -= deny
    lost |= deny
    if "flanking" in deny:
        flanking_count = 0
    imposed = ch.imposed | frozenset(keyword_denials.PREFIX + keyword for keyword in prohibited)
    return replace(ch, granted=frozenset(granted), lost=frozenset(lost), abilities=abilities, imposed=imposed, flanking_count=flanking_count)


# -- animation (agent A2): layer 4 type changes, layer 5 colors, layer 6 "loses all abilities" ----
COMMANDER_PLATE = "Protection from each color not in your commander's color identity"  # (wave 43B: statics grants it; derive writes the colors in)
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


def _layer4(ch: Characteristics, effects: list[ContinuousEffect],
            own: list[tuple[float, dict[str, Any]]] | None = None) -> Characteristics:
    """613.1d in timestamp order: types set (205.1a: replacing) or added (205.1b: "in addition to
    its other types", "it's still a land", "artifact creature"; a crewed Vehicle, 702.122),
    supertypes gained (205.4b), creature types set (205.1b: the other subtypes stay) or added
    ("becomes a Goblin in addition …", 701.47a), "all creature types".
    -- conditional statics (wave 4B) -- ``own``: the object's own layer-4 statics whose conditions hold
    ("~ isn't a creature", "is a Knight in addition to its other types": (timestamp, definition)),
    interleaved with the resolved effects by timestamp (613.7)."""
    from app.rules.creature_types import CREATURE_TYPES

    types, subtypes, supers = ch.types, ch.subtypes, ch.supertypes
    ordered: list[tuple[tuple[float, int, int], Any]] = [((e.object_seq, 1, e.timestamp), e) for e in effects if e.layer == "4"]
    ordered += [((seq, 0, 0), d) for seq, d in own or ()]
    ordered.sort(key=lambda x: x[0])
    for _, e in ordered:
        if isinstance(e, dict):  # -- conditional statics (wave 4B) --
            l4 = e.get("layer4")
            if l4 is not None:  # -- attached events (wave 4L) -- an Aura's or Equipment's (app/rules/attached_types.py)
                if l4.get("set_types") is not None:  # 205.1a
                    types = frozenset(l4["set_types"]) | (types & frozenset({"Instant", "Sorcery"}))
                types = (types - frozenset(l4.get("remove_types") or ())) | frozenset(l4.get("add_types") or ())  # 205.1b
                supers = supers | frozenset(l4.get("add_supertypes") or ())
                supers = supers - frozenset(l4.get("remove_supertypes") or ())  # -- static permanents (wave 100D) -- "no longer snow" (Melting, 205.4)
                if l4.get("set_creature_types") is not None:
                    known = LAND_TYPES | ARTIFACT_TYPES | ENCHANTMENT_TYPES | SPELL_TYPES | BATTLE_TYPES
                    subtypes = frozenset(s for s in subtypes if s in known) | frozenset(l4["set_creature_types"])
                if l4.get("set_land_types") is not None:  # -- land types set (wave 12D) -- 305.7
                    subtypes = (subtypes - LAND_TYPES) | frozenset(l4["set_land_types"])
                if l4.get("set_artifact_types") is not None:  # -- layers (wave 22A) -- 205.1a: an artifact type set
                    subtypes = (subtypes - ARTIFACT_TYPES) | frozenset(l4["set_artifact_types"])
                subtypes = subtypes | frozenset(l4.get("add_subtypes") or ())
                if l4.get("all_creature_types"):
                    from app.rules.creature_types import CREATURE_TYPES as _ALL

                    subtypes = subtypes | _ALL
                subtypes = frozenset(s for s in subtypes if _subtype_fits(s, types))
                continue
            if e.get("set_types") is not None:  # -- as long as (wave 20B) -- 205.1a: "it's a land"
                types = frozenset(e["set_types"]) | (types & frozenset({"Instant", "Sorcery"}))
            types = (types - frozenset(e.get("remove_types") or ())) | frozenset(e.get("add_types") or ())  # (205.1b: "creature in addition …")
            supers = supers - frozenset(e.get("remove_supertypes") or ())  # (wave 42A) 205.4: "isn't legendary if it's a token" (Aeve)
            subtypes = subtypes | frozenset(e.get("add_subtypes") or ()) | (CREATURE_TYPES if e.get("all_creature_types") else frozenset())  # (wave 100K: 205.3m)
            subtypes = frozenset(s for s in subtypes if _subtype_fits(s, types))
            continue
        if e.set_types is not None:
            # (an instant or sorcery keeps that type, 205.1a: never on the battlefield, so moot)
            types = frozenset(e.set_types) | (types & frozenset({"Instant", "Sorcery"}))
        if e.add_types:
            types = types | frozenset(e.add_types)
        types = types - frozenset(e.remove_types)
        if e.add_supertypes:
            supers = supers | frozenset(e.add_supertypes)
        supers = supers - frozenset(e.remove_supertypes)  # -- activated (wave 100I) --
        if e.set_creature_types is not None:
            # (a subtype in no list is a creature type — or, on a planeswalker, a planeswalker type, which stays)
            known = LAND_TYPES | ARTIFACT_TYPES | ENCHANTMENT_TYPES | SPELL_TYPES | BATTLE_TYPES
            kept = frozenset(s for s in subtypes if s in known or (s not in CREATURE_TYPES and "Planeswalker" in types))
            subtypes = kept | frozenset(e.set_creature_types)
        if e.all_creature_types:
            subtypes = subtypes | CREATURE_TYPES
        if e.set_land_types is not None:  # -- land types set (wave 12D) -- 305.7, 205.1a: the old land types are gone
            subtypes = (subtypes - LAND_TYPES) | frozenset(e.set_land_types)
        if e.set_artifact_types is not None:
            subtypes = (subtypes - ARTIFACT_TYPES) | frozenset(e.set_artifact_types)
        if e.add_subtypes:
            subtypes = subtypes | frozenset(e.add_subtypes)
        subtypes = subtypes - frozenset(e.remove_subtypes)
        subtypes = frozenset(s for s in subtypes if _subtype_fits(s, types))
    if (types, subtypes, supers) == (ch.types, ch.subtypes, ch.supertypes):
        return ch
    return replace(ch, types=types, subtypes=subtypes, supertypes=supers)


def _layer5(ch: Characteristics, effects: list[ContinuousEffect],
            own: list[tuple[float, dict[str, Any]]] | None = None) -> Characteristics:
    """613.1e in timestamp order: "becomes a green creature" replaces its colors, "colorless"
    removes them, "in addition to its other colors" adds (105.3). -- attached events (wave 4L) -- ``own``: statics
    of what is attached to it that set its colors ("is a green Elk creature"), interleaved by timestamp (613.7)."""
    colors = ch.colors
    ordered: list[tuple[tuple[float, int, int], Any]] = [((e.object_seq, 1, e.timestamp), e) for e in effects]
    ordered += [((seq, 0, 0), d) for seq, d in own or () if "set_colors" in d or "add_colors" in d]
    ordered.sort(key=lambda x: x[0])
    for _, e in ordered:
        if isinstance(e, dict):
            if "set_colors" in e:
                colors = frozenset(e["set_colors"])
            colors = colors | frozenset(e.get("add_colors") or ())
            continue
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


# -- review (wave 5R) -- ``_T.memo``: [state, info, table], the statics table of the table state one top-level ``derive`` reads
# (the table doesn't change while characteristics are derived; nested derives of other objects share it)


def derive(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None = None) -> Characteristics:
    """Current characteristics (``_derive``), the statics table read once for the whole derivation."""
    if _T.memo is not None or info is None:
        return _derive(state, card, ch, info)
    _T.borrow_graph = None
    sc = read_pass.current(state, info)
    if sc is None or not settled():  # (a derivation part-way reads a half-finished table: never kept, never served)
        _T.memo = [state, info, None]
        try:
            return _derive(state, card, ch, info)
        finally:
            _T.memo = None
            _T.borrow_graph = None
    # -- hints speed (wave 29A) -- in a read-only pass (app/rules/read_pass.py) the table does not change: the statics table, and what a
    # permanent of the table came to from the same printed values, are read once. (Only top-level derives are kept: one nested in
    # another derive reads the table as that one does.)
    kept = sc.derived.get(id(card))
    if kept is not None and kept[0] is card and (kept[1] is ch or kept[1] == ch):
        return kept[2]
    memo = _T.memo = [state, info, sc.table]
    try:
        out = _derive(state, card, ch, info)
    finally:
        sc.table = memo[2]
        _T.memo = None
        _T.borrow_graph = None
    if state.cards.get(card.id) is card:  # (a probe's copy of a card is never kept)
        sc.derived[id(card)] = (card, ch, out)
    return out


def settled() -> bool:
    """-- hints speed (wave 29A) -- Is no derivation part-way (no ``derive`` running, no group layers being solved, no re-entrant layer 4
    or characteristic-defining read)? Only then does a question about the table get the answer it has when nothing is half-finished,
    so only then may a read-only pass keep it or serve it (app/rules/read_pass.py)."""
    return _T.memo is None and not (_T.depth or _T.solving or _T.l4 or _T.cda)
# -- end review (wave 5R) --


def prepared(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> Characteristics:
    """The characteristics layer 4 starts from: layer 1 — copy effects (613.2a), face-down status (613.2b), and the overlays that are
    part of what the object is (a bestowed Aura, a prototyped permanent)."""
    # -- copy system (wave 2F): layer 1 — copy effects (613.2a), face-down status (613.2b) --
    from app.rules.copying import layer1

    ch = layer1(state, card, ch, info)
    from app.rules import stack_faces

    ch = stack_faces.apply(state, card, ch, info)
    if state.rules is not None and state.rules.bestowed:  # -- keywords (wave 15E) -- 702.103b: a bestowed Aura (spell or permanent)
        from app.rules import bestow

        if bestow.is_bestowed(state, card):
            ch = bestow.overlay(ch)
    if state.rules is not None and state.rules.payments:  # -- casting extras (wave 18E) -- 718.3b: a prototyped spell / permanent
        from app.game.rules_state import copy_recipe_of
        from app.rules import prototype

        # (review 18E: a copy effect on it gives it the copied object's values instead, 718.3b values being copiable: 707.2)
        if prototype.is_prototyped(state, card) and copy_recipe_of(state.rules, state.rules.object_id(card.id)) is None:
            ch = prototype.overlay(ch)
    return ch


def subtype_cdas(card: CardInstance, ch: Characteristics) -> Characteristics:
    """604.3a/613.2: the source's chosen land subtype precedes other type effects.

    The choice is not copiable (707.2), so apply this after copy values are read.
    """
    picked = card.choices.get('Chosen basic land type')
    if picked not in LAND_TYPES or 'Land' not in ch.types:
        return ch
    from app.rules import scripts, type_statics

    if not any(d.get('static') == 'chosen_land_type' for d in scripts.definitions(ch).values()):
        return ch
    changed = replace(ch, subtypes=(ch.subtypes - LAND_TYPES) | frozenset({picked}))
    return type_statics.with_gained_mana(ch, changed, True)


def source_text71(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> Characteristics:
    """A source's layer3 text generates later static effects; layer6 grants do not."""
    if state.rules is None or not (card.zone.endswith(':battlefield') or card.zone == 'stack'):
        return ch
    oid = state.rules.object_id(card.id)
    found = [e for e in state.rules.effects if e.layer == '3' and oid in e.affected]
    if not any(e.text_change71 is not None for e in found) and not state.rules.color_words71 and not card.stickers101:
        return ch
    return name_changes(ch, found, [], info, state, card)


def name_changes(ch: Characteristics, effects: list[ContinuousEffect],
                 attached45: list[tuple[float, dict[str, Any]]], info: CardInfo | None = None,
                 state: GameState | None = None, card: CardInstance | None = None) -> Characteristics:
    """Shared layer3 stage for final derivation and dependency positions (201.5)."""
    names: list[tuple[tuple[float, int, int], str]] = [
        ((stamp, 0, 0), definition["set_name"]) for stamp, definition in attached45
        if definition.get("set_name") is not None]
    names.extend(((effect.object_seq, 1, effect.timestamp), effect.set_name)
                 for effect in effects if effect.layer == "3" and effect.set_name is not None)
    from app.rules import text_global_word71, text_word_changes71

    changes = [((float(e.object_seq), 1, e.timestamp), e.text_change71) for e in effects
               if e.layer == '3' and e.text_change71 is not None]
    if state is not None and card is not None:
        changes += text_global_word71.global_changes(state, card, info)
    ordered: list[tuple[tuple[float, int, int], str | None, Any]] = [(stamp, name, None) for stamp, name in names] + [(stamp, None, change) for stamp, change in changes]
    if card is not None:
        ordered += [((p.object_seq, 1, p.timestamp), None, {'sticker101': p.sticker.text, 'position': p.position})
                    for p in card.stickers101 if p.sticker.kind == 'name']

    for _, name, change in sorted(ordered, key=lambda item: item[0]):
        if change is not None:
            if isinstance(change, dict) and 'sticker101' in change:
                from app.rules import stickers101

                ch = stickers101.name_change(ch, str(change['sticker101']), int(change['position']))
                continue
            ch = text_word_changes71.apply(ch, change, getattr(info, 'name_at', None))
            continue
        if name is not None and name != ch.name:
            from app.rules.copying import renamed

            # 201.5: self references still name this object after its name changes.
            # Preserve native slots and provenance; copiable values remain untouched.
            ch = replace(ch, name=name, oracle_text=renamed(ch.oracle_text, ch.name, name),
                         abilities=tuple(replace(a, text=renamed(a.text, ch.name, name),
                                                 cost=renamed(a.cost, ch.name, name) if a.cost else a.cost)
                                         for a in ch.abilities))
    return ch


def _derive_probe(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo) -> Characteristics:
    from app.rules.layer_dependency_graph import StaticTable, solve_field

    base = statics(state, info)
    raw = base.raw if isinstance(base, StaticTable) else base
    solved = solve_field(state, info, raw, card)
    previous = _T.probe
    _T.probe = solved
    try:
        field = [(cid, c.controller) for cid, c in solved.state.cards.items() if c.zone.endswith(":battlefield")]
        expanded = _extend_statics(solved.state, info, solved.table.detached(), solved.wiped, field)
        if not isinstance(expanded, StaticTable):
            raise TypeError("Prospective field lost its dependency operations")
        _T.probe = replace(solved, table=expanded)
        return _derive(state, card, ch, info)
    finally:
        _T.probe = previous


def _derive(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None = None) -> Characteristics:
    """Current characteristics: printed + continuous effects in layer order + counters. With
    ``info``, static abilities of permanents apply too (layers 6, 7b, 7c and rules imposed on the
    object it's attached to), and the object's own characteristic-defining P/T (7a, every zone)."""
    if info is not None and card.zone.endswith(":battlefield") and state.rules is not None \
            and _T.probe is None and not _T.solving and probing(state, card):
        return _derive_probe(state, card, ch, info)
    if card.face_down and card.zone.endswith(':exile'):
        # CR 406.3a: no current characteristics, even when someone may look.
        # Casting reads the prospective face-up spell separately (406.3b).
        return Characteristics(name='', face_down=True)
    ch = subtype_cdas(card, prepared(state, card, ch, info))
    from app.rules.characteristics import provenance

    ch = provenance(card, ch)
    ch = replace(ch, on_battlefield=card.zone.endswith(":battlefield"),
                 object_counters=frozenset(k for k, n in card.counters.items() if n > 0),
                 object_ring_bearer=bool(state.rules and card.zone.endswith(":battlefield")
                                         and state.rules.ring_bearers.get(card.controller) == state.rules.object_id(card.id)))
    from app.rules import stickers101

    effects = affecting(state, card, info) + stickers101.continuous(state, card)
    each_amounts: dict[int, int] = {}
    attached45 = _attached45(state, card, info)  # -- attached events (wave 4L) -- "Enchanted creature is a … creature"
    ch = name_changes(ch, effects, attached45, info, state, card)
    start = ch  # Abilities after layers 1-3, before layers 4-6 take any away.
    # -- layers (wave 22A) -- group statics of layers 4 and 5 ("Each land is a Swamp in addition …", "Nonbasic lands are Mountains.",
    # "All permanents are colorless.": 613.1d-e, 305.7), the objects each began applying to found as the table was solved (613.6, 613.8)
    from app.rules.layer_dependency_graph import StaticTable

    table = statics(state, info) if info is not None and state.rules is not None and card.zone.endswith(":battlefield") else None
    outside_self: list[dict[str, Any]] = []
    linked4: list[tuple[float, dict[str, Any]]] = []
    if isinstance(table, StaticTable) and card.id in table.layer4_orders:
        linked4 = [(float(node.key[0]), node.definition) for node in table.layer4_orders[card.id]
                   if node.definition is not None and 'linked_traits_values' in node.definition]
        ch = table.layer4(card.id, ch)
        ch = table.layer5(card.id, ch)
    else:
        own4 = _own_layer4(state, card, info) + attached45
        from app.rules import linked_aggregates

        linked4 = linked_aggregates.traits_layer4(state, card, info) if card.id not in _T.l4 else []
        own4 += linked4
        from app.rules import group_layers, outside_battlefield_self, type_statics

        # CR 113.6c: these self effects stop before battlefield entry probes. Read
        # layer-1 abilities so copying transfers the ability, not its derived values.
        outside_self = (outside_battlefield_self.parts(ch)
                        if not card.zone.endswith(':battlefield') and card.ability is None else [])
        outside4: list[tuple[float, dict[str, Any]]] = [(timestamp(state, card.id), d) for d in outside_self]
        own4 += outside4

        before4 = ch
        outside_types = _layer4(ch, [], outside4) if outside4 else ch
        group4, group5 = group_layers.entries(state, card, outside_types, info)
        # A group effect on creature cards depends on the self effect making this
        # a creature (613.8): it must see that type even if its source is older.
        ch = _layer4(outside_types, effects, own4 + group4)  # layer 4: type-changing (animation, agent A2: also layer 5 below)
        ch = type_statics.with_gained_mana(before4, ch, any(e.layer == "4" and e.set_land_types is not None for e in effects)
                                           or any((d.get("layer4") or {}).get("set_land_types") for _, d in attached45 + group4))
        # -- end layers --
        ch = _layer5(ch, effects, attached45 + _own_layer5(state, card, info) + group5)  # -- ability words (wave 9C) --
    if ch.is_creature or (not card.zone.endswith(':battlefield') and 'Vehicle' in ch.subtypes):
        effects += stickers101.continuous(state, card, pt=True)
    from app.rules import attack_requirements

    imposed = {rule for e in effects for rule in e.imposes}  # "can't block this turn" …
    imposed |= {marker for e in effects for marker in attack_requirements.instances(e.imposes, e.id)}
    imposed |= _group_imposed(state, card, ch, info)
    hits: list[Static] = []
    ability_statics: list[Static] = []
    borrowed: list[tuple[int, Any]] = []  # -- borrowed abilities (wave 18F) -- (the lending static's timestamp, the ability)
    kwc = keyword_counters(state, card)  # -- counters (wave 5H) --
    on_field = card.zone.endswith(":battlefield") and state.rules is not None
    if state.rules is not None and on_field and state.rules.object_id(card.id) in state.rules.suspected:  # -- suspect (wave 12A) -- 701.60c
        kwc = [*kwc, ((timestamp(state, card.id), 0, 0), "menace")]
        imposed.add("cant_block")
    if info is not None and on_field and _T.depth == 0:
        view = _view(state, info)
        table = statics(state, info)
        ability_statics = [st for st in table if "_abilities" in (st.definition.get("who") or "") and _grants(st.definition)]
        tkey = _table_key(state) if any(st.definition.get("conditions") or st.gate or st.definition.get("each")
                                        for st in table) else ()
        _T.depth += 1
        try:
            # a static's subject is read from the object after layer 4 and the resolved layer-6 effects
            hits, rules = _hits(view, table, card, _layer6(ch, [], effects, kwc), tkey)
            imposed |= rules
            ch = _layer6(ch, hits, effects, kwc)
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
                    ch = _layer6(ch, hits, effects, kwc)
            # "… gets +1/+1 for each Elf you control": the count, read now (611.3a), while other
            # objects' characteristics are read without statics (as a condition's are)
            each_amounts = {id(st): _each_amount(view, st, tkey, card) for st in hits if st.definition.get("each")}
            if _T.borrow_capture is None and any(st.definition.get("abilities_of") for st in hits):  # "has all activated abilities of …" (app/rules/abilities_of.py)
                from app.rules import abilities_of

                borrowed = [(st.seq, ab) for st in hits if st.definition.get("abilities_of") for ab in abilities_of.collect(view, st, card)]
        finally:
            _T.depth -= 1
    elif effects or kwc:
        ch = _layer6(ch, [], effects, kwc)
    wipe = _wipe_key(effects)  # (animation, agent A2: "loses all abilities" beats earlier grants, 613.7)
    # -- attached events (wave 4L) -- an Aura's "loses all abilities"
    from app.rules.attached_types import wipe_key

    static_wipes = [wipe_key(st) for st in hits if st.definition.get("lose_all")]
    if static_wipes:
        wipe = max([*static_wipes, *([wipe] if wipe is not None else [])])
    if _T.borrow_capture is not None:
        _T.borrow_capture[card.id] = [st for st in hits if st.definition.get("abilities_of") and
                                    (wipe is None or (st.seq, 0, 0) > wipe)]
    grants: list[tuple[Static, int, str, tuple[int, ...]]] = [(st, ordinal, text, ()) for st in hits if wipe is None or (st.seq, 0, 0) > wipe
              for ordinal, text in enumerate(st.definition["grants"])]
    if grants:  # layer 6: granted abilities, numbered after the printed ones (100, 101, …)
        from app.rules.scripts import granted_ability

        extra = []
        # -- most-played cards (wave 43B) -- "has protection from each color that's not in your commander's color identity" (Commander's Plate): one protection ability for each
        # color outside the combined identity of its controller's commanders (903.4); none at all without a commander (the ruling 2020-11-10); a commander with no color
        # in its identity gives protection from all five
        if any(text == COMMANDER_PLATE for _, _, text, _ in grants):
            expanded: list[tuple[Static, int, str, tuple[int, ...]]] = []
            for st, ordinal, text, expansion in grants:
                if text != COMMANDER_PLATE:
                    expanded.append((st, ordinal, text, expansion))
                    continue
                owner = state.cards.get(st.source)
                if owner is None or info is None or not any(c.owner == owner.controller and c.commander_key for c in state.cards.values()):
                    continue
                from app.rules.casting import commander_identity

                identity = commander_identity(state, owner.controller, info)
                expanded += [(st, ordinal, f"Protection from {name}", (*expansion, part)) for part, (name, letter) in enumerate( (("white", "W"), ("blue", "U"), ("black", "B"), ("red", "R"), ("green", "G")))
                             if letter not in identity]
            grants = expanded
        from app.rules import derived_protection

        if info is not None:
            # Color-set readers need the table through layer five, never recursively
            # expand another layer-six protection grant on the same object.
            _T.depth += 1
            try:
                grants = [(st, ordinal, line, (*expansion, part)) for st, ordinal, text, expansion in grants
                          for part, line in enumerate(derived_protection.static_lines(_view(state, info), text, st.source, ch))]
            finally:
                _T.depth -= 1
        from app.rules import quoted_prevention_loss47

        for k, (st, ordinal, text, expansion) in enumerate(grants):
            if quoted_prevention_loss47.lost(text, ch.name, st.key, effects):
                continue
            if "‹granter›" in text and state.rules is not None:  # -- granted from object (wave 18F) -- 607.1a: the granting object
                text = text.replace("‹granter›", f"‹granter#{state.rules.object_id(st.source)}›")
            if text in _chosen.PROTECTION:  # -- attached events (wave 25D) -- the granting Aura's own recorded color (wave 53B: or card type, or creature type)
                src = state.cards.get(st.source)
                player = _chosen.player_of(_view(state, info), src.id) if src is not None and info is not None and text == 'Protection from the chosen player' else None
                line = _chosen.protection_line(text, src.choices, player_id=player) if src is not None else None
                if line is None:
                    continue
                text = line
            ab = granted_ability(text)
            if ab is not None:
                keeps = st.definition.get("keeps")  # (702.16n: attachments.host_problem)
                owner = state.cards.get(st.source)
                extra.append(replace(ab, index=100 + k, keeps=None if keeps is None else f"self:{st.source}" if keeps == "self"
                                     else f"yours:{owner.controller}" if keeps == "yours" and owner is not None else keeps))  # (wave 53B: "Auras and Equipment you control", the granting Aura's controller)
                if _T.grant_capture45 is not None:
                    _T.grant_capture45.record(state, card, st, ordinal, expansion, text)
        ch = replace(ch, abilities=ch.abilities + tuple(extra))
    lent = tuple({ab.index: ab for seq, ab in borrowed if wipe is None or (seq, 0, 0) > wipe}.values())
    if lent:
        ch = replace(ch, abilities=ch.abilities + lent)
    ch = _granted_by_effects(ch, effects, wipe)
    if info is not None and not on_field and _T.depth == 0 and state.rules is not None and card.zone.endswith((":hand", ":graveyard")):
        from app.rules import (
            zone_grants,  # -- zone keyword grants (wave 25A) -- "Each creature card in your hand has cycling {1}{U}."
        )

        ch = zone_grants.apply(state, card, ch, info)
        from app.rules import dynamic_zone_keyword_costs56

        ch = dynamic_zone_keyword_costs56.apply(state, card, ch, info)
    if info is not None and _T.depth == 0 and state.rules is not None and card.zone == "stack" and card.ability is None:
        from app.rules import (
            kicked_spell_outcomes59,
            spell_grants,  # -- spell grants (wave 28C) -- "Instant and sorcery spells you control have lifelink." (613.1f, 604.1)
        )

        ch = kicked_spell_outcomes59.apply_stack(state, card, ch, info)
        ch = spell_grants.apply(state, card, ch, info)
    # Pure layer-7 effects asking about abilities see the completed layer 6, including
    # quoted/borrowed abilities appended above (613.1f, 613.4). Their sources have
    # already passed the statics table's ability-loss filtering.
    if ability_statics and info is not None:
        _T.depth += 1
        try:
            late, _unused = _hits(_view(state, info), ability_statics, card, ch, _table_key(state))
        finally:
            _T.depth -= 1
        hits = [st for st in hits if st not in ability_statics] + late
        hits.sort(key=lambda st: st.seq)
    # 208.3: a noncreature permanent has no power/toughness, including a
    # Vehicle. Copiable printed values remain unchanged; a later derivation
    # after crew/animation restores them and reapplies saved 208.3a effects.
    if on_field and not ch.is_creature:
        return _with_rules(state, card, replace(ch, power=None, toughness=None, pt=None, base_pt=None), info, imposed)
    # layer 7
    setters: list[tuple[tuple[int, int, int], int | None, int | None]] = []
    setters += [((timestamp(state, card.id), 0, 0), d['base'][0], d['base'][1]) for d in outside_self]
    setters += [((int(seq), 0, 0), d['linked_traits_values']['power'], d['linked_traits_values']['toughness']) for seq, d in linked4]
    for st in hits:  # 7b: static "has base power and toughness N/N" (613.4b), by its source's timestamp
        if st.definition.get("base"):
            setters.append(((st.seq, 0, 0), st.definition["base"][0], st.definition["base"][1]))
        elif st.definition.get("base_mv"):  # -- layers (wave 22A) -- "base power and toughness each equal to its mana value" (Opalescence)
            setters.append(((st.seq, 0, 0), int(ch.mana_value), int(ch.mana_value)))
        elif (st.definition.get("each") or {}).get("set"):  # -- most-played cards II (wave 45A) -- "base power and toughness X/X, where X is …" (Aettir and Priwen, Dollmaker's Shop)
            setters.append(((st.seq, 0, 0), each_amounts.get(id(st), 0), each_amounts.get(id(st), 0)))
    for e in effects:  # 7b: resolved setting effects, interleaved by timestamp (613.7)
        if e.layer == "7b":
            dyn = None
            if e.dyn_power110e is not None and info is not None:  # -- Ms. Marvel (wave 110E) -- 613.4b: "base power is equal to the number of cards in your hand", read now (611.3a)
                from app.rules import values

                dyn = values.evaluate(_view(state, info), {"controller": card.controller, "source_card": card.id}, e.dyn_power110e)
            setters.append(((e.object_seq, 1, e.timestamp), e.power if dyn is None else dyn, e.toughness))
    setters.sort(key=lambda x: x[0])
    power, toughness = _num(ch.power), _num(ch.toughness)
    if info is not None and (power is None or toughness is None):
        cda_p, cda_t = _cda(state, card, ch, info)  # 7a: the object's own characteristic-defining ability (613.4a)
        power = cda_p if cda_p is not None else power
        toughness = cda_t if cda_t is not None else toughness
        if (power is None or toughness is None) and _lost_cda(start, ch):  # -- review (wave 22A) -- its "*" CDA was taken away
            power = power if power is not None else _star_zero(ch.power)  # (305.7, 613.1f; Dress Down, Blood Moon on Ashaya):
            toughness = toughness if toughness is not None else _star_zero(ch.toughness)  # 208.5, "*" has no value: 0 ("1+*": 1)
    if ch.is_creature:  # CR 208.5: a permanent animated without printed P/T has 0/0.
        power = 0 if ch.power is None and power is None else power
        toughness = 0 if ch.toughness is None and toughness is None else toughness
    if (power is None or toughness is None) and not setters:
        return _with_rules(state, card, ch, info, imposed)  # 7a: a characteristic-defining "*" stays unknown
    p, t = power or 0, toughness or 0
    for _, sp, stt in setters:
        p = sp if sp is not None else p
        t = stt if stt is not None else t
    base = (p, t)  # -- base power (wave 30J) -- 208.4b, 613.4b: what a CDA (7a) and the setting effects (7b) left, before any modification (7c, counters)
    for st in hits:  # 7c: static modifications (613.4c) …
        p += st.definition["p"]
        t += st.definition["t"]
        each = st.definition.get("each")
        if each is not None and not each.get("set"):  # "… gets +1/+1 for each Elf you control" (613.4c, a dynamic amount)
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
    if on_field and info is not None:  # -- counters (wave 24C) -- 122.1j: a hone counter on an Equipment gives +1/+0 to the creature it's attached to
        p += _hone(state, card, info)
    for e in effects:  # … and resolved ones
        if e.layer == "7c":
            p += e.power or 0
            t += e.toughness or 0
    for e in effects:
        if e.layer == "7d":
            p, t = t, p
    return _with_rules(state, card, replace(ch, pt=(p, t), base_pt=base), info, imposed)


def _hone(state: GameState, card: CardInstance, info: CardInfo) -> int:
    """-- counters (wave 24C) -- 122.1j: the hone counters on the Equipment attached to this creature (613.4c: counters, layer 7c)."""
    from app.rules import characteristics as chars

    return sum(c.counters.get("hone", 0) for c in state.cards.values()
               if c.attached_to == card.id and c.counters.get("hone", 0) > 0 and c.zone.endswith(":battlefield")
               and "Equipment" in chars.of(c, info).subtypes)


# -- conditional statics (wave 4B) ----------------------------------------------------------------------------


def _impending_layer4(state: GameState, card: CardInstance, info: CardInfo | None) -> list[tuple[float, dict[str, Any]]]:
    """-- cast keywords (wave 43D) -- 702.176a: "As long as this permanent's impending cost was paid and it has a time counter on it, it's not a creature."
    (its own static, 613.1d: removing the type removes the creature types too, 205.3d); the cast record says the cost was paid, the counters are read
    now. Nothing here reads characteristics, so every reader gets it (as ``_own_layer4``)."""
    r = state.rules
    if r is None or not card.counters.get("time") or not card.zone.endswith(":battlefield"):
        return []
    rec = r.payments.get(r.object_id(card.id))
    if rec is None or rec.alternative != "impending" or info is None:
        return []
    if not any("impending" in a.keywords for a in copiable(state, card, info).abilities if a.kind == "keywords"):
        return []
    return [(float(timestamp(state, card.id)), {"remove_types": ["Creature"], "add_subtypes": []})]


def _own_layer4(state: GameState, card: CardInstance, info: CardInfo | None,
                table: list[Static] | None = None) -> list[tuple[float, dict[str, Any]]]:
    """The object's own layer-4 statics whose conditions hold now (and, wave 43D, impending's)."""
    return _impending_layer4(state, card, info) + _own_layer4_statics(state, card, info, table)


def _own_layer4_statics(state: GameState, card: CardInstance, info: CardInfo | None,
                        table: list[Static] | None = None) -> list[tuple[float, dict[str, Any]]]:
    """The object's own layer-4 statics whose conditions hold now ("As long as your devotion to red is less than
    five, ~ isn't a creature."; app/rules/statics.py ``_layer4_parts``). Applied for every reader, also while
    another static's condition reads this object (``_T.depth`` > 0): their conditions never read characteristics
    (statics ``_layer4_safe``: counters on the source, devotion from copiable mana costs (700.5a), life)."""
    if info is None or state.rules is None or not card.zone.endswith(":battlefield") or card.id in _T.l4:
        return []
    # -- review (wave 4R) -- (cheap first: only an object whose own copiable abilities have such a static reads the
    # table's statics — whose cache key is a pass over the battlefield, once per derive otherwise)
    from app.rules import scripts
    from app.rules import statics as grammar

    def safe_self_dictionary(d: dict[str, Any]) -> bool:
        return d.get("who") == "self" and "layer4" in d and (not d.get("layered") or probing(state, card)) and all(grammar._layer4_safe(c) for c in d.get("conditions") or ())

    if not any(d["kind"] == "static" and ("remove_types" in d or "add_subtypes" in d or "add_types" in d or safe_self_dictionary(d))
               for d in scripts.definitions(source_text71(state, card, copiable(state, card, info), info)).values()):
        return []
    table = [st for st in (statics(state, info) if table is None else table) if st.source == card.id and st.gate is None
             and ("remove_types" in st.definition or "add_subtypes" in st.definition or "add_types" in st.definition or safe_self_dictionary(st.definition))]
    incoming = probing(state, card)
    if incoming:
        # 614.12: its own type-changing static applies as it would exist on
        # the battlefield, even though it is absent from the battlefield table.
        table = [Static(card.id, card.controller, d, timestamp(state, card.id))
                 for d in scripts.definitions(source_text71(state, card, copiable(state, card, info), info)).values()
                 if d["kind"] == "static" and ("remove_types" in d or "add_subtypes" in d or "add_types" in d or safe_self_dictionary(d))]
    if not table:
        return []

    condition_state = state
    if incoming:
        # Include the entering object's mana symbols in its own devotion.
        # This scratch view evaluates only its own safe layer-4 conditions;
        # its other abilities never affect simultaneous incoming objects.
        zones = {k: [cid for cid in ids if cid != card.id] for k, ids in state.zones.items()}
        zones.setdefault(card.zone, []).append(card.id)
        condition_state = state.model_copy(update={"cards": {**state.cards, card.id: card}, "zones": zones})
    view = _view(condition_state, info)
    _T.l4.add(card.id)
    try:
        # (wave 11E: "is the chosen type in addition to its other types" adds the type chosen as it entered, 614.12a)
        return [(st.seq, {**st.definition, "add_subtypes": [t for t in [card.choices.get("Chosen creature type", "").strip()] if t]}
                 if st.definition.get("chosen_type") else st.definition) for st in table
                if grammar.conditions_hold(view, st.definition, source=card, controller=st.controller)]
    finally:
        _T.l4.discard(card.id)


def _own_layer5(state: GameState, card: CardInstance, info: CardInfo | None,
                table: list[Static] | None = None) -> list[tuple[float, dict[str, Any]]]:
    """-- ability words (wave 9C) -- the object's own color statics whose conditions hold now ("As long as there are seven or
    more cards in your graveyard, this creature gets +1/+1, is black, …"; statics ``_color_safe``: conditions that never
    read the colors being derived)."""
    if info is None or state.rules is None or not card.zone.endswith(":battlefield") or card.id in _T.l4:
        return []
    from app.rules import scripts

    if not any(d["kind"] == "static" and d.get("who") == "self" and "set_colors" in d
               for d in scripts.definitions(source_text71(state, card, copiable(state, card, info), info)).values()):
        return []
    table = [st for st in (statics(state, info) if table is None else table) if st.source == card.id and st.gate is None
             and st.definition.get("who") == "self" and "set_colors" in st.definition]
    if not table:
        return []
    from app.rules import statics as grammar

    view = _view(state, info)
    _T.l4.add(card.id)
    try:
        return [(st.seq, st.definition) for st in table
                if grammar.conditions_hold(view, st.definition, source=card, controller=st.controller)]
    finally:
        _T.l4.discard(card.id)


def _grants(d: dict[str, Any]) -> bool:
    """Does the static change characteristics (layers 6-7)? A rules-only static ("Creatures your
    opponents control can't block.") is applied by ``_with_rules`` instead."""
    return bool(d["p"] or d["t"] or d.get("base") or d.get("base_mv") or d["keywords"] or d["grants"] or d.get("each") or d.get("abilities_of") or d.get("linked_traits")
                or d.get("lose_keywords") or d.get("lose_all") or d.get("deny_keywords") or d.get("chosen_keywords"))  # -- attached events (wave 4L) -- (wave 49B: the chosen abilities)


def _attached45(state: GameState, card: CardInstance, info: CardInfo | None,
                table: list[Static] | None = None) -> list[tuple[float, dict[str, Any]]]:
    """-- attached events (wave 4L) -- the type/color statics of the Auras and Equipment attached to it."""
    if info is None or state.rules is None or not card.zone.endswith(":battlefield"):
        return []
    if not any(c.attached_to == card.id for c in state.cards.values()):
        return []
    from app.rules.attached_types import layer45

    return layer45(state, card, statics(state, info) if table is None else table)


# -- dynamic values (agent F): "for each …" modifications (7c) and characteristic-defining P/T (7a) --
_EACH_CACHE: dict[tuple, int] = {}
_CDA_CACHE: dict[tuple, tuple[int | None, int | None]] = {}


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
    other = '"other":true' in repr(each["value"]) or "'relative'" in repr(each["value"])  # (wave 6C: about ``card``)
    key = (tkey, st.source, st.controller, repr(each["value"]), card.id if other else "")
    hit = _EACH_CACHE.get(key) if tkey else None
    if hit is None:
        if len(_EACH_CACHE) > 4096:
            _EACH_CACHE.clear()
        from app.rules import linked_aggregates

        ctx = {**linked_aggregates.source_context(view, view.state.cards[st.source], st.definition), 'other_than': card.id}
        hit = values.evaluate(view, ctx, each["value"])
        if tkey:
            _EACH_CACHE[key] = hit
    return hit


def _lost_cda(start: Characteristics, now: Characteristics) -> bool:
    """Did layers 4-6 take away the object's characteristic-defining P/T ability (it had one before them, it has none now)?"""
    from app.rules import scripts

    def has(ch: Characteristics) -> bool:
        return any(d.get("static") == "cda" and (d.get("p") is not None or d.get("t") is not None) for d in scripts.definitions(ch).values())

    return has(start) and not has(now)


def _star_zero(value: str | None) -> int | None:
    try:
        return sum(int(x) for x in (value or "*").replace("*", "0").split("+"))
    except ValueError:
        return None


def _cda(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo) -> tuple[int | None, int | None]:
    """Layer 7a (613.4a): the object's own characteristic-defining ability that defines its power
    and/or toughness ("~'s power and toughness are each equal to the number of lands you control",
    app/rules/statics.py ``parse_cda``). It functions in every zone (604.3); "you" is its
    controller, or its owner for a card that has none (108.4a). A card played by hand (``manual``
    mode) keeps its printed "*" (unknown). A count that leads back to this object (a loop of CDAs
    reading each other's power) reads it as unknown rather than recursing (613.8: no dependency
    order is modelled beyond that)."""
    r = state.rules
    if r is None or card.id in _T.cda or r.card_mode(card.id) == "manual":
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
    ctx = {"controller": controller, "source_card": card.id, "source_object": r.object_id(card.id), "unknown_choice_raises": True}
    _T.cda.add(card.id)
    try:
        p = values.evaluate(view, ctx, d["p"]) if d["p"] is not None else None
        t = values.evaluate(view, ctx, d["t"]) if d["t"] is not None else None
    except values.NoChosenPlayer:  # -- chosen type (wave 16F) -- before "As ~ enters, choose …" is answered: not known yet (not 0)
        return None, None
    finally:
        _T.cda.discard(card.id)
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
    if info is not None and card.zone.endswith(":battlefield") and state.rules is not None and _T.depth == 0:
        from app.rules import attack_requirements
        from app.rules import statics as grammar

        view = _view(state, info)
        table = [st for st in statics(state, info) if st.definition["static"] == "grant" and st.definition.get("rules")]
        tkey = _table_key(state) if any(st.definition.get("conditions") or st.gate for st in table) else ()
        _T.depth += 1
        try:
            for index, st in enumerate(table):
                d = st.definition
                rules = [r.replace("@src", st.source) for r in _own(d["rules"], st.controller, card.owner)]
                markers = attack_requirements.instances(rules, f"static:{st.source}:{st.seq}:{index}")  # (wave 5C: per source)
                if (set(rules) | markers) <= imposed or not _gate_open(view, st, tkey):
                    continue
                source = view.state.cards[st.source]
                if not grammar.applies(view, d, source=source, controller=st.controller, card=card, ch=ch, conditions=True):
                    continue
                if any(grammar._mentions(c, ("self_stat",)) for c in d.get("conditions") or ()):
                    # -- static_other (wave 42A) -- "~ can't be blocked if her power is 1 or less" (Stature): a rule of the source itself (``applies`` holds only for
                    # it), judged on its own power after layer 7 (613.4), right here where that is known; never cached (it is the object's, not the table's)
                    _T.pt[card.id] = ch.pt
                    try:
                        holds = grammar.conditions_hold(view, d, source=source, controller=st.controller)
                    finally:
                        _T.pt.pop(card.id, None)
                else:
                    holds = _conditions(view, st, tkey)
                if holds:
                    imposed.update(rules)
                    imposed.update(markers)
        finally:
            _T.depth -= 1
    if imposed:
        ch = replace(ch, imposed=ch.imposed | frozenset(imposed))
    return ch


def rule_pt(card_id: str, stat: str) -> int | None:
    """-- static_other (wave 42A) -- the power / toughness of the object whose own rule static is being judged by ``_with_rules`` (None: not now)."""
    pt = _T.pt.get(card_id)
    return None if pt is None else pt[0 if stat == "power" else 1]


def _own(rules: list[str], controller: str, owner: str = "") -> list[str]:
    """-- keyword actions & face-down (wave 3F) -- a rule naming "@you" ("goaded:@you": 701.15b) names the
    static's controller; (-- group choices (wave 53D) --) "@owner", the owner of the object the rule is on ("can't attack its owner")."""
    return [r.replace("@you", controller).replace("@owner", owner) for r in rules]


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
    groups = [e for e in r.effects if e.who is not None and e.declaration_window is None]
    if not groups:
        return set()
    from app.rules import attack_requirements, selectors

    view = _view(state, info)
    out: set[str] = set()
    for e in groups:
        markers = attack_requirements.instances(e.imposes, e.id)
        if e.who is None or (set(e.imposes) | markers) <= out:
            continue
        src = e.source_card if e.source_card and r.object_id(e.source_card) == e.source else None
        if selectors.matches(view, selectors.from_key(e.who), card, ch, e.controller, src):
            out |= set(e.imposes) | markers
    return out


Layer = Literal["1", "2", "3", "4", "5", "6", "7a", "7b", "7c", "7d"]
Duration = Literal["end_of_turn", "permanent", "end_of_combat", "next_turn", "end_of_next_turn"]  # (wave 31C: "next_turn" — a copy effect "until your next turn", copying.add_copy_effect)


@world_native80
def add_effect(plan: Plan, *, affected: list[str], layer: Layer, source: str | None, controller: str,
               power: int | None = None, toughness: int | None = None, add_keywords: tuple[str, ...] = (),
               remove_keywords: tuple[str, ...] = (), add_types: tuple[str, ...] = (), duration: Duration = "end_of_turn",
               label: str = "", imposes: tuple[str, ...] = (), who: str | None = None,
               source_card: str | None = None, add_subtypes: tuple[str, ...] = (),
               **animation: Any) -> ContinuousEffect:
    """``animation`` (agent A2): the extra ``ContinuousEffect`` fields of a "becomes a …" effect
    (set_types, add_supertypes, set_creature_types, all_creature_types, set_colors, add_colors,
    remove_abilities, add_abilities)."""
    from app.rules import keyword_denials

    blocked = keyword_denials.capture(plan, affected) if add_keywords or animation.get("add_abilities") else {}
    r = plan.rules
    r.timestamp += 1
    effect = ContinuousEffect(id=f"e{r.timestamp}", affected=affected, layer=layer, source=source, controller=controller,
                              power=power, toughness=toughness, add_keywords=list(add_keywords),
                              remove_keywords=list(remove_keywords), blocked_keywords=blocked, add_types=list(add_types),
                              add_subtypes=list(add_subtypes), duration=duration,
                              imposes=list(imposes), who=who, source_card=source_card if who else None,
                              timestamp=r.timestamp, object_seq=r.next_object,
                              label=label[:120], markers=[], **animation)
    r.effects.append(effect)
    return effect


@world_native80
def end_of_turn(plan: Plan) -> None:
    """514.2: "until end of turn" effects end in the cleanup step."""
    r = plan.rules
    r.effects = [e for e in r.effects if e.duration not in ("end_of_turn", "end_of_combat")]  # (a combat a turn ended in, 18E review)
    from app.rules import delayed

    delayed.end_of_next_turn(plan)  # -- end of next turn (wave 32C) -- "until the end of your next turn" ends in the cleanup of that turn
    control_sync(plan)  # -- control (wave 3K) -- a Threaten effect ends: the creature goes back (613.1b)


# -- control (wave 3K): layer 2 (613.1b) -----------------------------------------------------------------
# The table keeps a permanent on its controller's side with ``controller`` set; this keeps that in line
# with the control-changing effects: resolved effects ("gain control of target creature until end of
# turn": ``ContinuousEffect.new_controller``, locked to the objects it began with, 611.2c) and the static
# abilities of Auras ("You control enchanted creature."). The latest timestamp wins (613.7); a permanent
# no effect controls any more goes back to its previous controller (which may differ from its owner), unless a player moved it by hand (only the cards
# an effect moved are in ``RulesState.control_changed``). The object is the same one throughout (no zone
# change: 400.7 doesn't apply), but a new controller restarts "summoning sickness" (302.6: tracked by
# ``controlled_since``), and the permanent leaves combat (506.4: the table action does that).
def control_sync(plan: Plan) -> None:
    """Apply layer 2 to the table, and end "for as long as …" effects it makes untrue (611.2b),
    until nothing changes."""
    r = plan.rules
    if r is None or not (r.effects or r.control_changed or r.control_baselines or any(c.attached_to for c in plan.state.cards.values())):
        return
    from app.rules import delayed

    for _ in range(8):
        delayed.expire(plan)
        if not _control_pass(plan):
            return


def _control_pass(plan: Plan) -> bool:
    from app.rules import scripts

    state, r = plan.state, plan.rules
    battle = {cid: c for cid, c in state.cards.items() if c.zone.endswith(":battlefield") or (c.zone == "stack" and c.ability is None)}
    live = set(plan.live())
    # A zone change makes a fresh object even when its card id is reused. Phasing does not.
    existing = {plan.oid(c) for c in state.cards.values() if c.zone.endswith((":battlefield", ":phased")) or (c.zone == "stack" and c.ability is None)}
    for oid in list(r.control_baselines):
        if oid not in existing:
            del r.control_baselines[oid]
            cid = oid.rsplit(".", 1)[0]
            r.control_changed = [x for x in r.control_changed if x != cid]
    entries: dict[str, list[tuple[tuple[int, int, int], str]]] = {}
    by_object = {plan.oid(c): cid for cid, c in battle.items()} if any(e.layer == "2" for e in r.effects) else {}
    for e in r.effects:
        if e.layer == "2" and e.new_controller:
            for oid in e.affected:
                if oid in by_object:
                    entries.setdefault(by_object[oid], []).append(((e.object_seq, 1, e.timestamp), e.new_controller))
    for cid, c in battle.items():  # "You control enchanted creature." (a static: whatever it is attached to now, 611.3a)
        if c.attached_to in battle and not c.face_down and c.controller in live and (d := next(
                (d for d in scripts.definitions(copiable(state, c, plan.info)).values() if d.get("static") == "control"), None)) is not None:
            # (-- attached (wave 100F) -- "The monarch controls enchanted creature." (Fealty to the Realm): the monarch now, at the Aura's timestamp; none: no effect (the rulings))
            who = state.table.monarch if d.get("to") == "monarch" else c.controller
            if who is not None:
                entries.setdefault(c.attached_to, []).append(((timestamp(state, cid), 0, 0), who))
    changed = False
    for cid in sorted(set(entries) | set(r.control_changed)):
        card = battle.get(cid)
        if card is None:
            if cid in state.cards and state.cards[cid].zone.endswith(":phased"):
                continue  # -- review (wave 14R) -- 702.26b/f: judged again once it phases in (its effect may have ended meanwhile)
            r.control_changed = [x for x in r.control_changed if x != cid]
            continue
        valid = [p for _, p in sorted(entries.get(cid, ())) if p in live]  # (800.4a: a departed player's effects ended)
        if valid:
            want: str | None = valid[-1]
            if cid not in r.control_changed and want != card.controller:
                r.control_baselines[plan.oid(card)] = card.controller
                r.control_changed.append(cid)
            elif r.control_baselines.get(plan.oid(card)) == want:
                # A remaining control effect can agree with the underlying controller.
                # Once that baseline is restored there is no change left to remember.
                r.control_baselines.pop(plan.oid(card), None)
                r.control_changed = [x for x in r.control_changed if x != cid]
        elif cid in r.control_changed:
            # Older saves lack the baseline; retain their historical owner fallback.
            baseline = r.control_baselines.pop(plan.oid(card), card.owner)
            want = baseline if baseline in live else None
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
    stack = {r.object_id(cid) for cid, c in state.cards.items() if c.zone == "stack" and c.ability is None}
    stack6 = {r.object_id(cid) for cid, card in state.cards.items() if card.zone == "stack" and card.ability is None
              and ((entry := r.stack.get(cid)) is None or entry.kind == "spell")}
    r.effects = [e for e in r.effects if e.who is not None or set(e.affected) & live
                 or (e.layer == "2" and set(e.affected) & stack)
                 or (e.layer == "6" and bool(set(e.affected) & stack6))]
