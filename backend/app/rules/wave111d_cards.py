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
    from app.rules import scripts, selectors

    if body.strip() == "Choose a counter on target enchantment you control. Put another counter of that kind on it.":
        # Dathon, His Heart Open: Animation Module's "Choose a counter on target permanent. Give that permanent another counter of that kind." (one
        # instruction, the kind chosen as it resolves, 608.2c; 122.1) with an enchantment you control as its target (115.1)
        got = scripts.parse_effects("Choose a counter on target permanent. Give that permanent another counter of that kind.")
        sel = selectors.parse("enchantment you control")
        if got is None or got[1] != "sel:{}" or sel is None:
            return None
        return copy.deepcopy(got[0]), sel.key(), got[2]
    native = _BODIES.get(body.strip())
    if native is None:
        return None
    got = scripts.parse_effects(native)
    return copy.deepcopy(got) if got is not None else None


_ABILITIES = {
    # Tasha Yar, Out of Time: "this card" is the card its cost exiled (400.7j: the ability's effects can find it in exile), copied as embalm's is
    # (702.128a, 707.2: its copiable values); the token is sacrificed by a delayed trigger (603.7)
    "{2}{R}, Exile this card from your graveyard: Create a token that's a copy of this card. Sacrifice it at the beginning of the next end step. Activate "
    "only as a sorcery.":
        "{2}{R}, Exile this card from your graveyard: Create a token that's a copy of the card exiled to activate this ability. Sacrifice it at the "
        "beginning of the next end step. Activate only as a sorcery.",
    # Dathon, His Heart Open: in a cast trigger, "it" is the spell that was cast, judged as the trigger resolves (608.2h if it has left the stack)
    "Whenever you cast an enchantment spell, draw a card. If it's a Saga spell, Dathon deals 2 damage to each opponent.":
        "Whenever you cast an enchantment spell, draw a card. If that spell is a Saga, Dathon deals 2 damage to each opponent.",
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    """The definition of one of the exact abilities above, read as its native wording, else None."""
    from dataclasses import replace

    from app.rules import scripts

    native = _ABILITIES.get(ability.text)
    return scripts.define(replace(ability, text=native), ch) if native is not None else None


def component(part: str) -> CostComponent | None:
    """One exact cost part, else None."""
    from app.rules import costs as C

    if part == "Put this card from your graveyard on the bottom of your library":
        return C.CostComponent(C.EXILE_FROM_GRAVEYARD, to_bottom110i=True, text=part)  # (no selector: this card itself, 113.6m)
    return None
