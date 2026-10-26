"""-- last cards (wave 110C) -- exact wordings read through wordings the grammar already knows.

* Torrent Elemental: 113.6m, the ability works only from exile (casting.ability_cost sets ``exile_only110c``); the effect is the Mister Immortal move.
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.oracle import AbilityText

_TORRENT = "{3}{B/G}{B/G}: Put this card from exile onto the battlefield tapped. Activate only as a sorcery."


_MONUMENT = "{3}: This artifact becomes a 9/9 Phyrexian Construct artifact creature, loses all abilities, and gains indestructible and toxic 9. Activate only if there are nine or more lands with different names among the basic, Sphere, and Locus lands you control."
_NINE = "there are nine or more lands with different names among the basic, Sphere, and Locus lands you control"


def condition(text: str) -> dict[str, Any] | None:
    """Monument to Perfection (201.2, 205.3i): lands you control that are basic or a Sphere or a Locus, counted by different names."""
    from app.rules import selectors

    if text != _NINE:
        return None
    sel = selectors.parse("land you control")
    assert sel is not None
    return {"value": {"distinct": "names", "among": replace(sel, extras=("basic_or_sub110c:Sphere|Locus",)).key()}, "op": ">=", "n": 9}


def definition(ability: AbilityText, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text == _MONUMENT:
        # 611.2a / 613.1: no duration, so permanent; the abilities it gains come after "loses all abilities" (timestamp order, 613.7)
        animate = scripts.parse_effects("~ becomes a 9/9 Phyrexian Construct artifact creature, loses all abilities, and gains toxic 9 until end of turn.")
        indestructible = scripts.parse_effects("~ gains indestructible until end of turn.")
        base = scripts.define(replace(ability, text="{3}: ~ gains indestructible until end of turn. Activate only if there are nine or more lands with different names among the basic, Sphere, and Locus lands you control."), ch)
        if animate is None or indestructible is None or base is None:
            return None
        effects = [{**e, "duration": "permanent"} for e in (*animate[0], *indestructible[0])]
        return {**base, "effects": effects}
    if ability.text == _TORRENT:
        return scripts.define(replace(ability, text=_TORRENT.replace("Put this card from exile onto", "Return this card from your graveyard or from exile to")), ch)
    return None
