"""-- offering (wave 51H) -- 702.48a: "[Quality] offering" is "As an additional cost to cast this spell, you may sacrifice a [quality] permanent. If you chose to pay the additional
cost, this spell's total cost is reduced by the sacrificed permanent's mana cost, and you may cast this spell any time you could cast an instant." The sacrifice is chosen with the other
choices (702.48b, 601.2b) and paid with the cost (601.2h): an optional cost of the cast (cost_changes.optional_offers), whose line is also casting.flash_if's timing leniency."""

from __future__ import annotations

import re
from typing import Any

from app.rules import costs as C
from app.rules import mana as M

LINE = re.compile(r"^([a-z]+) offering$")


def component(quality: str) -> C.CostComponent | None:
    """The sacrifice of a permanent you control of that type or subtype (701.21a); None when the cost grammar can't read the quality."""
    key = C._selector(f"{quality} you control", zone="battlefield")
    return C.CostComponent(C.SACRIFICE, amount=1, selector=key, text=f"Sacrifice {'an' if quality[0] in 'AEIOU' else 'a'} {quality}", offering=True) if key else None


def definition(t: str) -> dict[str, Any] | None:
    """The line "Moonfolk offering" (reminder text stripped): the shape of a card's own flash condition (permissions.flash_condition), here "if you sacrifice a Moonfolk"."""
    m = LINE.fullmatch(t)
    quality = m[1].capitalize() if m else ""
    if not quality or component(quality) is None:
        return None
    return {"kind": "static", "static": "permission", "zone": "any", "once": False, "flash": True, "self": True, "play": False, "cast": True, "filter": None,
            "flash_if": {"offering": quality}, "effects": []}


def reduce(cost: M.ManaCost, paid: M.ManaCost) -> M.ManaCost:
    """702.48c, 118.7: the total ``cost`` reduced by the sacrificed permanent's mana cost ``paid``. Generic reduces generic only (118.7a); colored and colorless mana reduce mana of
    that type, an excess reduces generic mana (118.7b-d, snow 118.7g); a hybrid or Phyrexian symbol is the half the payer prefers (118.7e-f: the one that takes the most off, a
    colored half first). Never below {0} (118.7). ponytail: {X} in the sacrificed cost is 0 on the battlefield (107.3); the choices are made greedily, hybrids after the fixed symbols."""
    colored, less = list(cost.colored), paid.generic
    for sym in paid.colored:
        if sym != M.SNOW and sym in colored:
            colored.remove(sym)
        else:
            less += 1

    def saving(h: str) -> int:
        room = max(0, cost.generic - less)  # (generic mana still to take off)
        return min(int(h), room) if h.isdigit() else 1 if h in colored else min(1, room)

    for halves in (*paid.hybrid, *(tuple(p.split("/")) for p in paid.phyrexian)):
        pick = max(halves, key=lambda h: (saving(h), h in colored))
        if pick.isdigit():
            less += int(pick)
        elif pick in colored:
            colored.remove(pick)
        else:
            less += 1
    return M.ManaCost(max(0, cost.generic - less), tuple(colored), cost.hybrid, cost.phyrexian, cost.x, cost.unsupported)
