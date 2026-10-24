"""An attack-triggered, temporary Citadel-style top-library authority."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

_TEXT = 'Whenever Gwenom attacks, until end of turn, you may look at the top card of your library any time and you may play cards from the top of your library. If you cast a spell this way, pay life equal to its mana value rather than pay its mana cost.'
def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts
    if ability.text.strip().casefold() not in (_TEXT.casefold(), _TEXT.replace('Gwenom', '~').casefold()):
        return None
    native = scripts.define(replace(ability, text='Whenever this creature attacks, you gain 1 life.'), ch)
    if native is None:
        raise ValueError('Native Gwenom attack shell unavailable')
    return {**native, 'optional': False, 'effects': [{'do': 'grant_play', 'player': 'you', 'zone': 'library_top', 'zone_owner': 'you', 'look_top': True, 'play': True, 'cast': True, 'free': True, 'life_mv': True, 'until': 'end_of_turn'}]}
