"""Continuous effects and the layer system (CR 611, 613), researched against CR 2026-09-25.

An effect lives in ``rules.effects`` and names the **rules objects** it affects. Effects from a
resolving spell or ability lock their set of objects when they begin (611.2c); because the set
holds object ids, an affected permanent that changes zones is a new object and the effect no
longer applies to it (400.7). Printed characteristics are never overwritten: ``derive`` computes
the current ones each time.

Implemented today (each with tests): layer 4 (types added, e.g. a crewed Vehicle), layer 6 (abilities: keywords gained / lost) and layer 7
power/toughness: 7a characteristic-defining values are left to the printed card (``*`` stays
unknown), 7b setting effects, 7c modifying effects **and counters** (613.4c), 7d switching.
Within a layer, effects apply in timestamp order (613.7). Dependencies (613.8) and layers 1–5
(copy, control, text, type, color) are next; the model already carries the layer number.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Literal

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


_ANTHEM_CACHE: dict[tuple, list[tuple[str, str, dict]]] = {}


def anthems(state: GameState, info: CardInfo) -> list[tuple[str, str, dict]]:
    """Static P/T and keyword grants on the battlefield (source card, its controller, definition),
    read from printed abilities; cached by what is on the battlefield."""
    r = state.rules
    live = {p for p in state.seat_order if not state.players[p].left} - (set(r.conceded) | set(r.lost) if r else set())
    key = tuple(sorted((cid, c.controller, c.face_down, c.card_id or c.name, r.card_mode(cid) if r else "")
                       for cid, c in state.cards.items() if c.zone.endswith(":battlefield")))
    hit = _ANTHEM_CACHE.get(key)
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
            if d["kind"] == "static" and d.get("static") == "anthem":
                out.append((cid, c.controller, d))
    if len(_ANTHEM_CACHE) > 256:
        _ANTHEM_CACHE.clear()
    _ANTHEM_CACHE[key] = out
    return out


def _anthem_applies(src: str, controller: str, d: dict, card: CardInstance, ch: Characteristics) -> bool:
    if not (ch.is_land if d.get("lands") else ch.is_creature) or (d["other"] and src == card.id):
        return False
    if d.get("commander"):  # "Commander creatures you own"
        return card.commander_key is not None and card.owner == controller
    if d["scope"] == "you" and card.controller != controller:
        return False
    if d["scope"] == "opponents" and card.controller == controller:
        return False
    if d["sub"] and d["sub"] not in ch.subtypes:
        return False
    return not d["tokens"] or card.is_token


def derive(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None = None) -> Characteristics:
    """Current characteristics: printed + continuous effects in layer order + counters. With
    ``info``, static abilities of permanents (anthems, lords: layers 6 and 7c) apply too."""
    out = _derive_resolved(state, card, ch)
    if info is None or not card.zone.endswith(":battlefield") or state.rules is None:
        return out
    p = t = 0
    kws: set[str] = set()
    grants: list[str] = []
    for src, controller, d in anthems(state, info):
        if _anthem_applies(src, controller, d, card, out):
            p, t = p + d["p"], t + d["t"]
            kws |= set(d["keywords"])
            if d.get("grant"):
                grants.append(d["grant"])
    if not (p or t or kws or grants):
        return out
    pt = (out.pt[0] + p, out.pt[1] + t) if out.pt is not None else None
    out = replace(out, pt=pt, granted=out.granted | frozenset(kws))
    if grants:  # layer 6: granted abilities, numbered after the printed ones (100, 101, …)
        from app.rules.scripts import granted_ability

        extra = []
        for k, text in enumerate(grants):
            ab = granted_ability(text)
            if ab is not None:
                extra.append(replace(ab, index=100 + k))
        out = replace(out, abilities=out.abilities + tuple(extra))
    return out


def _derive_resolved(state: GameState, card: CardInstance, ch: Characteristics) -> Characteristics:
    effects = affecting(state, card)
    added = {t for e in effects if e.layer == "4" for t in e.add_types}  # layer 4: type-changing
    if added - ch.types:
        ch = replace(ch, types=ch.types | frozenset(added))
    granted: set[str] = set()
    lost: set[str] = set()
    for e in effects:  # layer 6, timestamp order
        if e.layer == "6":
            granted |= set(e.add_keywords)
            granted -= set(e.remove_keywords)
            lost |= set(e.remove_keywords)
            lost -= set(e.add_keywords)
    power, toughness = _num(ch.power), _num(ch.toughness)
    if (power is None or toughness is None) and not any(e.layer == "7b" for e in effects):
        return replace(ch, granted=frozenset(granted), lost=frozenset(lost)) if effects else ch
    p, t = power or 0, toughness or 0
    for e in effects:
        if e.layer == "7b":
            p = e.power if e.power is not None else p
            t = e.toughness if e.toughness is not None else t
    p += card.counters.get("+1/+1", 0) - card.counters.get("-1/-1", 0)  # counters are layer 7c
    t += card.counters.get("+1/+1", 0) - card.counters.get("-1/-1", 0)
    for e in effects:
        if e.layer == "7c":
            p += e.power or 0
            t += e.toughness or 0
    for e in effects:
        if e.layer == "7d":
            p, t = t, p
    return replace(ch, pt=(p, t), granted=frozenset(granted), lost=frozenset(lost))


Layer = Literal["1", "2", "3", "4", "5", "6", "7a", "7b", "7c", "7d"]
Duration = Literal["end_of_turn", "permanent"]


def add_effect(plan: Plan, *, affected: list[str], layer: Layer, source: str | None, controller: str,
               power: int | None = None, toughness: int | None = None, add_keywords: tuple[str, ...] = (),
               remove_keywords: tuple[str, ...] = (), add_types: tuple[str, ...] = (), duration: Duration = "end_of_turn",
               label: str = "") -> ContinuousEffect:
    r = plan.rules
    r.timestamp += 1
    effect = ContinuousEffect(id=f"e{r.timestamp}", affected=affected, layer=layer, source=source, controller=controller,
                              power=power, toughness=toughness, add_keywords=list(add_keywords),
                              remove_keywords=list(remove_keywords), add_types=list(add_types), duration=duration,
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
    r.effects = [e for e in r.effects if set(e.affected) & live]
