"""-- last cards (wave 110C) -- exact wordings read through wordings the grammar already knows.

* Torrent Elemental: 113.6m, the ability works only from exile (casting.ability_cost sets ``exile_only110c``); the effect is the Mister Immortal move.
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.oracle import AbilityText

_TORRENT = "{3}{B/G}{B/G}: Put this card from exile onto the battlefield tapped. Activate only as a sorcery."


TRESPASSER = "This creature gets +1/+0 until end of turn for each name sticker on it. It can't be blocked this turn."


def trespasser() -> Any:
    """123.2: +1/+0 for each name sticker on the creature (values: ``name_stickers110c``), then the unblockable rider."""
    from app.rules import wave110c_core

    effects, target, optional = wave110c_core.read("~ gets +1/+0 until end of turn. It can't be blocked this turn.")
    effects[0]["p"] = {"name_stickers110c": True}
    return effects, target, optional


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


_TUSK_TRIGGER = "Whenever you put an ability sticker on a creature, put a +1/+1 counter on that creature."
_TUSK_ACTIVATED = "{2}{G}{W}, {T}: You get {TK}. You may put a sticker on a nonland permanent you own."


def definition(ability: AbilityText, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text == _TUSK_TRIGGER:  # 123.2: the creature the sticker went on gets the counter (122.1)
        d = scripts.define(replace(ability, text=_TUSK_TRIGGER.replace("that creature", "~")), ch)
        return None if d is None else {**d, "effects": [{**e, "who": "event"} for e in d["effects"]]}
    if ability.text == _TUSK_ACTIVATED:  # 702.33h-like: a ticket counter, then an optional sticker on a nonland permanent you own (Done for the Day)
        base = scripts.define(replace(ability, text="{2}{G}{W}, {T}: You get {TK}."), ch)
        if base is None:
            return None
        put = {"do": "put_sticker101", "kind": None, "n": 1, "as": "placed101", "sel": 'sel:{"not_types":["Land"],"owner":"you"}'}
        return {**base, "effects": [*base["effects"], put]}

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
