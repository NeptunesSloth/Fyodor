"""Exact optional player target and entering-land controller recipes."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

CLIMBER = (
    "Whenever this creature attacks, up to one target player mills cards equal to this creature's power."
)
TECTONIC = "Whenever a land enters, tap all lands its controller controls."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != "triggered" or ability.text not in (CLIMBER, TECTONIC):
        return None
    from app.rules import scripts, selectors

    base = (
        "Whenever this creature attacks, target player mills cards equal to this creature's power."
        if ability.text == CLIMBER
        else "Whenever a land enters, its controller gains 1 life."
    )
    native = scripts.define(replace(ability, text=base), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    if ability.text == CLIMBER:
        if (out.get("target") or {}).get("what") != "player":
            return None
        group = out.pop("target")
        group.update(min=0, max=1)
        out["targets"] = [group]
    else:
        if out.get("cond", {}).get("event") != "enter":
            return None
        # The existing reference reads the original entering object's current
        # controller, or its last known controller after departure (608.2h).
        out["effects"] = [
            {
                "do": "tap",
                "who": f"controlled:ref:event.controller|{selectors.Selector(types=('Land',)).key()}",
            }
        ]
    return out
