"""Native selected kicker-X targeting and kicked damage read actual object/payment history."""
from __future__ import annotations

from dataclasses import replace
from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text != "When ~ enters, if it was kicked, gain control of target artifact with mana value X or less. If that artifact is an Equipment, attach it to ~.":
        return None
    native = scripts.define(replace(ability, text="When ~ enters, if it was kicked, gain control of target artifact with mana value X or less."), ch)
    attach = scripts.parse_effects("Attach target Equipment to ~.")
    equipment = selectors.parse("Equipment")
    if native is None or attach is None or equipment is None:
        return None
    return {**native, "effects": [{**native["effects"][0], "as": "skydiver61_target"},
            {"do": "only_if", "cond": {"object": "ref:skydiver61_target", "is": equipment.key()}, "n": 1},
            {**attach[0][0], "src": "ref:skydiver61_target"}]}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    if body != "Destroy target nonblack creature. It can't be regenerated. If this spell was kicked, ~ deals damage equal to that creature's power to the creature's controller.":
        return None
    native = scripts.parse_effects("Destroy target nonblack creature. It can't be regenerated. ~ deals damage equal to that creature's power to that creature's controller.")
    if native is None or len(native[0]) != 3:
        return None
    return [*native[0][:2], {"do": "kicked_gate", "kicked": True, "n": 1}, native[0][2]], native[1], False
