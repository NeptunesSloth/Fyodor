"""Exact blocker/pair color trigger and attacked-player target relation."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
RIGHTEOUS = (
    "Whenever a creature blocks a black or red creature, the blocking creature gets +1/+1 until end of turn."
)
MENTOR = "Whenever you attack a player, target creature that's attacking that player gains first strike until end of turn."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != "triggered" or ability.text not in (RIGHTEOUS, MENTOR):
        return None
    from app.rules import scripts, selectors

    base = (
        "Whenever a creature blocks, it gets +1/+1 until end of turn."
        if ability.text == RIGHTEOUS
        else "Whenever you attack a player, target attacking creature gains first strike until end of turn."
    )
    native = scripts.define(replace(ability, text=base), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    if ability.text == RIGHTEOUS:
        # Native paired fact preserves objects=blocker, other=attacker. Do not
        # set other (which would deliberately swap the effect event subject).
        out["cond"]["event"] = "block_pair"
        # Top if is tested only when adding trigger; no resolving only_if.
        out["if"] = {"object": "ref:event_other", "is": selectors.Selector(colors=("B", "R")).key()}
    else:
        out["target"]["what"] = selectors.Selector(
            types=("Creature",), attacking=True, attacking_player=selectors.THAT_PLAYER
        ).key()
    return out
