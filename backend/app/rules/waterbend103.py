"""Optional waterbend is a declared additional cost, never a kicker alias."""

from __future__ import annotations

from typing import Any


def mana(optional: list[Any]) -> Any:
    import re

    from app.rules import mana as M

    symbols = []
    for item in optional:
        if item.kind == "waterbend103":
            match = re.fullmatch(r"Waterbend (\{\d+\})", item.text)
            if match is None:
                from app.game.errors import ActionError

                raise ActionError("Invalid optional waterbend cost")
            symbols.append(match[1])
    return M.parse_cost("".join(symbols))


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ch.name not in ("Spirit Water Revival", "Ruinous Waterbending", "Katara, Seeking Revenge"):
        return None
    text = ability.text.replace("this spell's additional cost was paid", "its waterbend cost was paid")
    if ch.name == "Katara, Seeking Revenge":
        text = text.replace(
            ", then discard a card unless her additional cost was paid.",
            ". If its waterbend cost wasn't paid, discard a card.",
        )
    if text == ability.text:
        return None
    from dataclasses import replace

    from app.rules import scripts

    return scripts.define(replace(ability, text=text), ch)
