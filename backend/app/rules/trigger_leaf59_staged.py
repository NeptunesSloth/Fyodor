"""Exact kicks-a-spell watcher; requires staged per-kicker event multiplicity."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
TEXT = "Whenever a player kicks a spell, you create a 1/1 green Saproling creature token."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != "triggered" or ability.text != TEXT:
        return None
    from app.rules import scripts

    native = scripts.define(
        replace(
            ability, text="Whenever a player casts a spell, you create a 1/1 green Saproling creature token."
        ),
        ch,
    )
    if native is None:
        return None
    out = copy.deepcopy(native)
    out["cond"].update(kicked=True, per_kicker=True)
    return out
