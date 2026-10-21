"""CR 603.3d: upkeep player chooses a target for another player's ability."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = (
    "At the beginning of each player's upkeep, destroy target nonartifact creature that player controls of their choice. "
    "It can't be regenerated."
)


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if "World" in ch.supertypes or ability.text != TEXT:
        return None
    from app.rules import scripts, selectors

    native = scripts.define(
        replace(
            ability,
            text="At the beginning of each player's upkeep, destroy target nonartifact creature. It can't be regenerated.",
        ),
        ch,
    )
    sel = selectors.parse("nonartifact creature that player controls")
    if native is None or sel is None or native.get("kind") != "triggered":
        return None
    return {**native, "target": {"what": sel.key()}, "target_choice": "event_player"}
