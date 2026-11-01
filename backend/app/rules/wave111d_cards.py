"""-- Star Trek one-offs (wave 111D) -- exact Oracle wordings whose parts the grammar already reads, put together here.

* "Put a +1/+1 counter on target creature you control. Untap it. Until end of turn, it gets +1/+1 and becomes a Doctor." (I'm a Doctor, Not a . . .;
  its reminder "It loses all other creature types." is 205.1a: a creature type set replaces the old ones): the pump and the type change are two
  effects of one resolution, both until end of turn (514.2), in layers 7c and 4 (613.1d, 613.4c).
* "Put this card from your graveyard on the bottom of your library" (Daniels, Temporal Agent): a cost that moves the card out of its owner's graveyard,
  so the ability works only there (113.6m), paid as Battlefield Scrounger's cost is (to the bottom of its owner's library, 401.4).
"""
from __future__ import annotations

import copy
from typing import Any

from app.rules.costs import CostComponent

Parsed = tuple[list[dict[str, Any]], Any, bool]

_BODIES = {
    "Put a +1/+1 counter on target creature you control. Untap it. Until end of turn, it gets +1/+1 and becomes a Doctor.":
        "Put a +1/+1 counter on target creature you control. Untap it. It gets +1/+1 until end of turn. Until end of turn, it becomes a Doctor.",
}


def parse(body: str) -> Parsed | None:
    """The native reading of one of the exact bodies above, else None."""
    from app.rules import scripts

    native = _BODIES.get(body.strip())
    if native is None:
        return None
    got = scripts.parse_effects(native)
    return copy.deepcopy(got) if got is not None else None


def component(part: str) -> CostComponent | None:
    """One exact cost part, else None."""
    from app.rules import costs as C

    if part == "Put this card from your graveyard on the bottom of your library":
        return C.CostComponent(C.EXILE_FROM_GRAVEYARD, to_bottom110i=True, text=part)  # (no selector: this card itself, 113.6m)
    return None
