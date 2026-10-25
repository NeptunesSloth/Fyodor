"""-- costs (wave 110D) -- activation-cost parts the generic parser doesn't read, put onto the existing cost machinery (app/rules/costs.py,
cost_payment.py). Researched against CR 2026-09-25.

* 601.2h, 118.3: a cost is paid in full or not at all, so "two creature cards from a single graveyard", "two untapped creatures that share a creature
  type" and "two cards that share a color" are constraints on the whole group chosen (``CostComponent.names``: "single_gy", "share_type",
  "share_color"), checked where the generic code checks "with the same name" / "with different names".
* 205.3m: creatures share a creature type when they have one in common; 105.2c: a colorless object shares no color with anything.
* 406.3 / 404: "from a graveyard" is any player's graveyard (``Selector.zone_owner`` None).
* 701.21a: "Sacrifice a suspected creature" (701.60: the designation), "Exile an instant or sorcery spell you control" (the spell leaves the stack and
  won't resolve; it isn't countered).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rules.costs import CostComponent
    from app.rules.plan import Plan

GROUPS = ("single_gy", "share_type", "share_color")


def component(part: str, card_name: str) -> CostComponent | None:
    from app.rules import costs as C
    from app.rules import selectors

    if part == "Exile an instant or sorcery spell you control":
        return C.CostComponent(C.EXILE, selector=selectors.Selector(zones=("stack",), controller="you", types=("Instant", "Sorcery")).key(), text=part)
    if part == "Sacrifice a suspected creature":
        return C.CostComponent(C.SACRIFICE, selector=selectors.Selector(types=("Creature",), controller="you", extras=("suspected",)).key(), text=part)
    if part == "Exile two creature cards from a single graveyard":
        return C.CostComponent(C.EXILE_FROM_GRAVEYARD, amount=2, names="single_gy", text=part,
                               selector=selectors.Selector(card=True, zones=("graveyard",), types=("Creature",)).key())
    if (m := re.fullmatch(r"Exile a (?P<t>[A-Z][a-z]+) card from a graveyard", part)) is not None:
        return C.CostComponent(C.EXILE_FROM_GRAVEYARD, text=part, selector=selectors.Selector(card=True, zones=("graveyard",), subtypes=(m["t"],)).key())
    if part == "Tap two untapped creatures you control that share a creature type":
        sel = selectors.Selector(types=("Creature",), controller="you", tapped=False)
        return C.CostComponent(C.TAP_OTHER, amount=2, names="share_type", selector=sel.key(), text=part)
    if part == "Reveal two cards from your hand that share a color":
        sel = selectors.Selector(card=True, zones=("hand",), zone_owner="you")
        return C.CostComponent("REVEAL_FROM_HAND", amount=2, names="share_color", selector=sel.key(), text=part)
    if (m := re.fullmatch(r"Tap five untapped attacking creatures you control named (?P<name>[A-Z][\w' -]+)", part)) is not None:
        sel = selectors.Selector(types=("Creature",), controller="you", tapped=False, attacking=True, extras=("name:" + m["name"],))
        return C.CostComponent(C.TAP_OTHER, amount=5, selector=sel.key(), text=part)
    return None


# "Sacrifice a creature named Feral Shadow, a creature named Breathstealer, and this creature" (Urborg Panther): three parts, one object each
_NAMED = re.compile(r"Sacrifice (?P<a>an? creature named [A-Z][\w' -]+?), (?P<b>an? creature named [A-Z][\w' -]+?), and this creature")


def rewrite(cost: str) -> str:
    return _NAMED.sub(r"Sacrifice \g<a>, Sacrifice \g<b>, Sacrifice this creature", cost)


def _sets(plan: Plan, comp: CostComponent, ids: list[str]) -> list[set[str]]:
    from app.rules.creature_types import CREATURE_TYPES

    out: list[set[str]] = []
    for cid in ids:
        card = plan.state.cards[cid]
        ch = plan.ch(card)
        out.append({card.zone} if comp.names == "single_gy" else set(ch.subtypes & CREATURE_TYPES) if comp.names == "share_type" else set(ch.colors))
    return out


def fit(plan: Plan, comp: CostComponent, ids: list[str]) -> bool:
    sets = _sets(plan, comp, ids)
    return bool(sets) and bool(set.intersection(*sets))


def payable(plan: Plan, comp: CostComponent, ids: list[str], need: int) -> bool:
    from collections import Counter

    counts = Counter(v for s in _sets(plan, comp, ids) for v in s)
    return any(n >= need for n in counts.values())


def graveyard_pool(plan: Plan, comp: CostComponent) -> list[str]:
    """"… from a graveyard": the cards of every graveyard (the selector names no owner)."""
    return [c for z, ids in plan.state.zones.items() if z.endswith(":graveyard") for c in ids]


def own_pool_only(comp: CostComponent) -> bool:
    from app.rules import selectors

    return comp.selector is None or selectors.from_key(comp.selector).zone_owner is not None


