"""Exact attack power and simultaneous highest-life definitions (staged)."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.effects import Context
    from app.rules.plan import Plan

CULTIVATOR = "Whenever this creature attacks, you may have other attacking creatures get +X/+X until end of turn, where X is this creature's power."
ARBITER = (
    "When this creature enters, each player's life total becomes the highest life total among all players."
)


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != "triggered" or ability.text not in (CULTIVATOR, ARBITER):
        return None
    from app.rules import scripts

    base = (
        "Whenever this creature attacks, other attacking creatures get +1/+1 until end of turn."
        if ability.text == CULTIVATOR
        else "When this creature enters, you gain 1 life."
    )
    native = scripts.define(replace(ability, text=base), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    if ability.text == CULTIVATOR:
        out["optional"] = True
        # X is a nonnegative result (107.1b); direct pump power is signed.
        value = {"plus": [{"power": "self"}, 0]}
        out["effects"][0].update(p=value, t=copy.deepcopy(value))
    else:
        out["effects"] = [{"do": "arbiter_highest54"}]
    return out


def arbiter_highest(plan: Plan, ctx: Context, effect: dict[str, Any]) -> bool:
    """Freeze signed highest once, then use native atomic life/replacement resume."""
    from app.rules import life_changes44

    if "values" not in effect:
        players = plan.live()
        if not players:
            return True
        highest = max(plan.state.players[p].life for p in players)
        # Keep this exact resolver instruction: native _then recognizes it and
        # can pause for replacement order. The serialized map stays frozen.
        effect.update(who="each_player", values={p: highest for p in players})
    return life_changes44.set_life(plan, ctx, effect)
