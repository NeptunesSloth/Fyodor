"""Exact self-block and self-attack leaves over native layer effects."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

WURM = "When this creature blocks, it loses defender."
FIREBOAR = "Whenever this creature attacks, switch its power and toughness until end of turn."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != "triggered" or ability.text not in (WURM, FIREBOAR):
        return None
    from app.rules import scripts

    base = (
        "When this creature blocks, it gets +0/+0 until end of turn."
        if ability.text == WURM
        else "Whenever this creature attacks, switch this creature's power and toughness until end of turn."
    )
    native = scripts.define(replace(ability, text=base), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    if ability.text == WURM:
        # CR611.2a: no duration is stated. Existing layer-6 removal lasts for
        # this ObjectRef's lifetime; it neither denies later grants nor copies.
        out["effects"] = [{"do": "grant", "who": "self", "remove": ["defender"], "duration": "permanent"}]
    return out
