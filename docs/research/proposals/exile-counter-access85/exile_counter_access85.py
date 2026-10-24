"""Counter-qualified dynamic exile access preserves current eligibility."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

LARA = ('Whenever ~ attacks, exile up to one target legendary artifact card or legendary land card from a graveyard '
        'and put a discovery counter on it. You may play a card from exile with a discovery counter on it this turn.')

def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts, selectors
    if scripts.self_text(ability.text, ch.name) != LARA:
        return None
    native = scripts.define(replace(ability, text=LARA.split(' You may play')[0]), ch)
    if native is None:
        return None
    selected = selectors.Selector(zones=('exile',), extras=('counter:discovery',)).key()
    return {**native, 'effects': [*native['effects'], {'do':'grant_play', 'zone':'exile', 'zone_owner':'any',
            'card_filter':selected, 'play':True, 'cast':True, 'once':True, 'until':'end_of_turn'}]}
