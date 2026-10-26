"""Thran Portal: "Mana abilities of this land cost an additional 1 life to activate." (601.2f/602.2b, 118.8: an additional cost, paid with the
rest; mana abilities have no stack, 605.3b). Read as the land's mana abilities carrying "Pay 1 life" in their cost, after every layer."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = "Mana abilities of this land cost an additional 1 life to activate."


def apply(ch: Any) -> Any:
    if not any(a.text == TEXT for a in ch.abilities):
        return ch
    from app.rules import mana as M

    out = []
    for a in ch.abilities:
        head, sep, tail = a.text.partition(": ")
        if sep and a.kind in ("activated", "mana") and "Pay 1 life" not in head and M.parse_mana_ability(a.text) is not None:
            a = replace(a, text=f"{head}, Pay 1 life: {tail}", cost=f"{a.cost}, Pay 1 life" if a.cost else head + ", Pay 1 life")
        out.append(a)
    return replace(ch, abilities=tuple(out))
