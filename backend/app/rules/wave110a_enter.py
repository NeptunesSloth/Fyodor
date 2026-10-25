"""-- entry types (wave 110A) -- "As a historic permanent you control enters, it becomes a 7/7 Dinosaur creature in addition to its other types."

614.12: a replacement that modifies how a permanent enters; 205.1b "in addition" adds the types, 613.4b sets base power and toughness.
The effect has no end (611.2a), so it is a permanent layer effect made right after the move (``after_entry``).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

_RE = re.compile(r"^as an? (?P<sel>historic permanent you control) enters, it becomes an? (?P<p>\d+)/(?P<t>\d+) (?P<sub>[A-Z][a-z]+) creature "
                 r"in addition to its other types$", re.I)


def static(t: str) -> dict[str, Any] | None:
    m = _RE.fullmatch(t.strip().rstrip("."))
    if m is None:
        return None
    return {"kind": "static", "static": "enter_become110a", "sel": m["sel"].lower(), "p": int(m["p"]), "t": int(m["t"]),
            "sub": m["sub"].capitalize(), "effects": []}


def apply(plan: Plan, card: CardInstance) -> None:
    from app.rules import layers, permissions, selectors

    for src, _, d in permissions._table_statics(plan.state, plan.info, {"enter_become110a"}):
        sel = selectors.parse(d["sel"])
        if sel is None or not selectors.matches(plan, sel, card, plan.ch(card), src.controller, src.id):
            continue
        layers.add_effect(plan, affected=[plan.oid(card)], layer="4", source=None, controller=src.controller, add_types=("Creature",),
                          add_subtypes=(d["sub"],), duration="permanent", label=f"{d['sub']} creature (enters)")
        layers.add_effect(plan, affected=[plan.oid(card)], layer="7b", source=None, controller=src.controller, power=d["p"],
                          toughness=d["t"], duration="permanent", label=f"{d['p']}/{d['t']} (enters)")
