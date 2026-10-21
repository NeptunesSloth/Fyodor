"""Exact target-controller conditional pump and hand Aura attachment leaves."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
KILLER = "When this creature enters, target creature an opponent controls gets -2/-2 until end of turn if that opponent controls no other creatures."
RESEARCHERS = "When this creature enters, you may put an Aura card from your hand onto the battlefield attached to this creature."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != "triggered" or ability.text not in (KILLER, RESEARCHERS):
        return None
    from app.rules import scripts, selectors

    base = (
        "When this creature enters, target creature an opponent controls gets -2/-2 until end of turn."
        if ability.text == KILLER
        else "When this creature enters, you may put an Aura card from your graveyard onto the battlefield attached to this creature."
    )
    native = scripts.define(replace(ability, text=base), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    if ability.text == KILLER:
        # Trailing if is a resolution-only test, not a target restriction.
        key = selectors.Selector(types=("Creature",), controller=selectors.THAT_PLAYER).key()
        gate = {
            "do": "only_if",
            "that": "tp:0",
            "cond": {"value": {"count": key}, "op": "==", "n": 1},
            "skip": 1,
        }
        out["effects"].insert(0, gate)
    else:
        effect = out["effects"][0]
        aura_selector = selectors.from_key(effect["sel"])
        effect["sel"] = selectors.replace(aura_selector, zones=("hand",)).key()
    return out
