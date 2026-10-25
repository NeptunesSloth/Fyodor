"""Crashing Wave composes native targets with an untargeted resolving distribution."""

from __future__ import annotations

from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if (
        ch.name != "Crashing Wave"
        or ability.text
        != "Tap up to X target creatures, then distribute three stun counters among any number of tapped creatures your opponents control."
    ):
        return None
    from dataclasses import replace

    from app.rules import counter_distribution, scripts, selectors

    native = scripts.define(replace(ability, text="Tap up to X target creatures."), ch)
    recipients = selectors.parse("tapped creatures your opponents control")
    if native is None or recipients is None:
        return None
    return {
        **native,
        "effects": [
            *native["effects"],
            {"do": counter_distribution.STEP, "who": recipients.key(), "n": 3, "kind": "stun"},
        ],
    }
