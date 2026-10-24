"""Paladin Class composes native turn pricing, levels and attack-target continuations."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

TAX = "Spells your opponents cast during your turn cost {1} more to cast."
ATTACK = "Whenever you attack, until end of turn, target attacking creature gets +1/+1 for each other attacking creature and gains double strike."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import permissions, scripts, selectors

    if ability.text == TAX:
        return permissions.define_static(
            "During your turn, spells your opponents cast cost {1} more to cast.", "static", ()
        )
    if ability.text == ATTACK:
        text = "Whenever you attack, target attacking creature gets +1/+1 for each other attacking creature until end of turn. It gains double strike until end of turn."
        native = scripts.define(replace(ability, text=text), ch)
        if native is None:
            return None
        amount = {
            "minus": [
                {
                    "count": selectors.Selector(
                        zones=("battlefield",), types=("Creature",), attacking=True
                    ).key()
                },
                1,
            ]
        }
        return {
            **native,
            "effects": [
                {**e, "p": amount, "t": amount} if e.get("do") == "pump" else e for e in native["effects"]
            ],
        }
    return None
