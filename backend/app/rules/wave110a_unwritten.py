"""-- wave 110A -- See the Unwritten: "Reveal the top eight cards of your library. You may put a creature card from among them onto the battlefield. Put the rest
into your graveyard." + "Ferocious — If you control a creature with power 4 or greater, you may put two creature cards onto the battlefield instead of one."

Scryfall ruling 2014-09-20: ferocious is checked as the spell resolves, before any card is put onto the battlefield; the two creature cards enter at the same time
(one pick of two); "instead" gives only the upgraded effect (never one card and then two). Built from the grammar's own "Draw a card. If you control a creature with
power 4 or greater, draw two cards instead." shape (only_if/skip), with the draws replaced by the picks. The Ferocious line is read as part of the first."""
from __future__ import annotations

from typing import Any

FIRST = "Reveal the top eight cards of your library. You may put a creature card from among them onto the battlefield. Put the rest into your graveyard."
FEROCIOUS = "Ferocious — If you control a creature with power 4 or greater, you may put two creature cards onto the battlefield instead of one."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = ability.text.strip()
    if text == FEROCIOUS:
        return {"kind": "spell", "effects": [], "target": None} if any(a.text.strip() == FIRST for a in ch.abilities) else None
    if text != FIRST or not any(a.text.strip() == FEROCIOUS for a in ch.abilities):
        return None
    base = scripts.parse_effects(FIRST)
    cond = scripts.parse_effects("Draw a card. If you control a creature with power 4 or greater, draw two cards instead.")
    if base is None or cond is None:
        return None
    look, pick, rest = base[0]
    swapped = [{**pick, "n": e["n"]} if e["do"] == "draw" else e for e in cond[0]]
    return {"kind": "spell", "effects": [look, *swapped, rest], "target": None}
