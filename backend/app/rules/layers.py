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
the printed card. Layers implemented (each with tests): 4 (types added, e.g. a crewed Vehicle),
6 (abilities: keywords gained / lost, quoted abilities granted, 613.1f), 7a (characteristic-defining
values are left to the printed card: ``*`` stays unknown), 7b (setting effects, incl. "base power
and toughness", 613.4b), 7c (modifying effects **and counters**, 613.4c), 7d (switching). Within a
layer, resolved effects apply in timestamp order (613.7); a static ability's effect has its
source's timestamp (613.7a), which the table doesn't track yet, so static effects apply before
resolved ones in each layer (in a stable order among themselves). Dependencies (613.8) aren't
modelled: a static's subject is read once, from the object as it is after layer 4 and the resolved
layer-6 effects (so "creatures with flying" doesn't see flying another static grants). Layers 1–5
(copy, control, text, color) are next; the model already carries the layer number.
"""

from __future__ import annotations

from dataclasses import replace
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


_STATIC_CACHE: dict[tuple, list[tuple[str, str, dict]]] = {}


def statics(state: GameState, info: CardInfo) -> list[tuple[str, str, dict[str, Any]]]:
    """Static grants and attached rules of permanents on the battlefield (source card, its
    controller, definition), read from printed abilities; cached by what is on the battlefield.
    Whether each applies to a given object, and its conditions, are evaluated by ``derive``."""
    r = state.rules
    live = {p for p in state.seat_order if not state.players[p].left} - (set(r.conceded) | set(r.lost) if r else set())
    key = tuple(sorted((cid, c.controller, c.face_down, c.card_id or c.name, c.token.text if c.token else "",
                        r.card_mode(cid) if r else "")
                       for cid, c in state.cards.items() if c.zone.endswith(":battlefield")))
    hit = _STATIC_CACHE.get(key)
    if hit is not None:
        return hit
    from app.rules import characteristics as chars
    from app.rules import scripts

    out = []
    for cid, c in state.cards.items():
        if not c.zone.endswith(":battlefield") or c.face_down or c.controller not in live or c.owner not in live:
            continue
        if r is not None and r.card_mode(cid) == "manual":
            continue
        for d in scripts.definitions(chars.of(c, info)).values():
            if d["kind"] == "static" and d.get("static") in ("grant", "attached_rule"):
                out.append((cid, c.controller, d))
    if len(_STATIC_CACHE) > 256:
        _STATIC_CACHE.clear()
    _STATIC_CACHE[key] = out
    return out


anthems = statics  # (the old name)


def _view(state: GameState, info: CardInfo) -> Plan:
    """A read-only view of this table (no copy) for the selector / condition evaluators."""
    from app.rules.plan import Plan

    view = Plan.__new__(Plan)
    view.state, view.info = state, info
    return view


_depth = 0  # re-entrancy: a static's subject or condition reading another object's characteristics


def derive(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None = None) -> Characteristics:
    """Current characteristics: printed + continuous effects in layer order + counters. With
    ``info``, static abilities of permanents apply too (layers 6, 7b, 7c and rules imposed on the
    object it's attached to)."""
    global _depth
    effects = affecting(state, card)
    added = {t for e in effects if e.layer == "4" for t in e.add_types}  # layer 4: type-changing
    if added - ch.types:
        ch = replace(ch, types=ch.types | frozenset(added))
    imposed = {rule for e in effects for rule in e.imposes}  # "can't block this turn" …
    imposed |= _group_imposed(state, card, ch, info)
    granted: set[str] = set()
    lost: set[str] = set()
    for e in effects:  # layer 6 (resolved effects), timestamp order
        if e.layer == "6":
            granted |= set(e.add_keywords)
            granted -= set(e.remove_keywords)
            lost |= set(e.remove_keywords)
            lost -= set(e.add_keywords)
    if effects or granted or lost:
        ch = replace(ch, granted=frozenset(granted), lost=frozenset(lost))
    hits: list[tuple[CardInstance, dict[str, Any]]] = []
    on_field = card.zone.endswith(":battlefield") and state.rules is not None
    if info is not None and on_field and _depth == 0:
        from app.rules import statics as grammar

        view = _view(state, info)
        _depth += 1
        try:
            for src, controller, d in statics(state, info):
                source = state.cards[src]
                if d["static"] == "attached_rule":
                    if _attached_rule_applies(source, d, card, ch):
                        imposed.update(d["imposes"])
                    continue
                if grammar.applies(view, d, source=source, controller=controller, card=card, ch=ch):
                    hits.append((source, d))
        finally:
            _depth -= 1
    if imposed:
        ch = replace(ch, imposed=ch.imposed | frozenset(imposed))
    # layer 6: static keyword and ability grants (613.1f)
    kws = {k for _, d in hits for k in d["keywords"]}
    grants = [text for _, d in hits for text in d["grants"]]
    if kws:  # (a resolved "loses …" effect has the later timestamp: it wins, see the module docstring)
        ch = replace(ch, granted=(ch.granted | frozenset(kws)) - ch.lost)
        if _depth == 0 and info is not None:
            # 613.8: a layer-7 effect on "creatures with flying" depends on layer-6 grants of flying:
            # its subject is read again now that layer 6 is applied.
            _depth += 1
            try:
                hits = [(source, d) for source, d in hits
                        if not _keyword_subject(d) or grammar.applies(view, d, source=source, controller=source.controller,
                                                                        card=card, ch=ch)]
                for src, controller, d in statics(state, info):
                    source = state.cards[src]
                    if d["static"] == "grant" and _keyword_subject(d) and (source, d) not in hits \
                            and grammar.applies(view, d, source=source, controller=controller, card=card, ch=ch):
                        hits.append((source, d))
            finally:
                _depth -= 1
    if grants:  # granted abilities, numbered after the printed ones (100, 101, …)
        from app.rules.scripts import granted_ability

        extra = []
        for k, text in enumerate(grants):
            ab = granted_ability(text)
            if ab is not None:
                extra.append(replace(ab, index=100 + k))
        ch = replace(ch, abilities=ch.abilities + tuple(extra))
    # layer 7
    bases = [d["base"] for _, d in hits if d.get("base")]
    power, toughness = _num(ch.power), _num(ch.toughness)
    sets = bases or any(e.layer == "7b" for e in effects)
    if (power is None or toughness is None) and not sets:
        return ch  # 7a: a characteristic-defining "*" the engine doesn't compute stays unknown
    p, t = power or 0, toughness or 0
    for base in bases:  # 7b: static "has base power and toughness N/N" (613.4b)
        p, t = base
    for e in effects:  # 7b: resolved setting effects
        if e.layer == "7b":
            p = e.power if e.power is not None else p
            t = e.toughness if e.toughness is not None else t
    for _, d in hits:  # 7c: static modifications (613.4c) …
        p += d["p"]
        t += d["t"]
    p += card.counters.get("+1/+1", 0) - card.counters.get("-1/-1", 0)  # … counters …
    t += card.counters.get("+1/+1", 0) - card.counters.get("-1/-1", 0)
    for e in effects:  # … and resolved ones
        if e.layer == "7c":
            p += e.power or 0
            t += e.toughness or 0
    for e in effects:
        if e.layer == "7d":
            p, t = t, p
    return replace(ch, pt=(p, t))


def _keyword_subject(d: dict[str, Any]) -> bool:
    """Does the static's subject ask about keyword abilities ("creatures with flying")?"""
    who = d["who"]
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
               source_card: str | None = None) -> ContinuousEffect:
    r = plan.rules
    r.timestamp += 1
    effect = ContinuousEffect(id=f"e{r.timestamp}", affected=affected, layer=layer, source=source, controller=controller,
                              power=power, toughness=toughness, add_keywords=list(add_keywords),
                              remove_keywords=list(remove_keywords), add_types=list(add_types), duration=duration,
                              imposes=list(imposes), who=who, source_card=source_card if who else None,
                              timestamp=r.timestamp,
                              label=label[:120])
    r.effects.append(effect)
    return effect


def end_of_turn(plan: Plan) -> None:
    """514.2: "until end of turn" effects end in the cleanup step."""
    r = plan.rules
    r.effects = [e for e in r.effects if e.duration != "end_of_turn"]


def prune(state: GameState) -> None:
    """Drop effects none of whose objects still exist (bookkeeping only; they couldn't apply)."""
    r = state.rules
    if r is None or not r.effects:
        return
    live = {r.object_id(cid) for cid, c in state.cards.items() if c.zone.endswith(":battlefield")}
    r.effects = [e for e in r.effects if e.who is not None or set(e.affected) & live]
