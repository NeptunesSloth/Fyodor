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
from app.rules.characteristics import Characteristics

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


def derive(state: GameState, card: CardInstance, ch: Characteristics) -> Characteristics:
    """Current characteristics: printed + continuous effects in layer order + counters."""
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
