"""-- last cards (wave 110C) -- exact wordings read through wordings the grammar already knows.

* Torrent Elemental: 113.6m, the ability works only from exile (casting.ability_cost sets ``exile_only110c``); the effect is the Mister Immortal move.
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.oracle import AbilityText

_TORRENT = "{3}{B/G}{B/G}: Put this card from exile onto the battlefield tapped. Activate only as a sorcery."


def definition(ability: AbilityText, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text == _TORRENT:
        return scripts.define(replace(ability, text=_TORRENT.replace("Put this card from exile onto", "Return this card from your graveyard or from exile to")), ch)
    return None
