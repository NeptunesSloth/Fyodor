"""Qualified searches whose found cards are split before their final destinations."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import selectors

    text = body.strip().lower().rstrip('.')
    base: dict[str, Any] = {'do': 'gifts', 'k': 2, 'max': 4, 'chooser': 'opponent', 'label': 'creature cards',
                            'different_names': True, 'chosen_to': 'library', 'rest': 'hand', 'packet': True}
    kind = 'creature card'
    optional = False
    exile = False
    if text == 'search your library for up to four creature cards with different powers and reveal them. an opponent chooses two of those cards. shuffle the chosen cards into your library and put the rest into your hand':
        base.update(different_names=False, different_power=True)
    elif text in ('you may search your library for exactly two cards not named ~ that have different names. if you do, reveal those cards. an opponent chooses one of them. put the chosen card into your hand and the other into your graveyard, then shuffle',
                  'you may search your library for exactly two cards not named burning-rune demon that have different names. if you do, reveal those cards. an opponent chooses one of them. put the chosen card into your hand and the other into your graveyard, then shuffle'):
        kind = 'card'
        base.update(k=1, max=2, excluded_name='Burning-Rune Demon', chosen_to='hand', rest='graveyard', label='cards')
        optional = True
    elif text in ('search your library and graveyard for up to four creature cards with different names that each have mana value x or less and reveal them. an opponent chooses two of those cards. shuffle the chosen cards into your library and put the rest onto the battlefield. exile ~',
                  'search your library and graveyard for up to four creature cards with different names that each have mana value x or less and reveal them. an opponent chooses two of those cards. shuffle the chosen cards into your library and put the rest onto the battlefield. exile ecological appreciation'):
        kind = 'creature card with mana value X or less'
        base.update(zones=['library', 'graveyard'], rest='battlefield')
        exile = True
    elif text == 'search your library for three creature cards and reveal them. if you reveal three cards with different names, choose one of them at random and put that card into your hand. shuffle the rest into your library':
        base.update(k=1, max=3, different_names=False, chooser='random_distinct_three', chosen_to='hand', rest='library')
    elif text in ('search your library for up to three monocolored cards with different names and exile them. an opponent chooses one of those cards. shuffle that card into your library. you may cast the other cards without paying their mana costs. exile ~',
                  'search your library for up to three monocolored cards with different names and exile them. an opponent chooses one of those cards. shuffle that card into your library. you may cast the other cards without paying their mana costs. exile emergent ultimatum'):
        kind = 'monocolored card'
        base.update(k=1, max=3, exile_first=True, rest='cast', label='monocolored cards')
        exile = True
    else:
        return None
    sel = selectors.parse(kind)
    assert sel is not None
    base['sel'] = sel.key()
    return ([base, *([{'do': 'exile', 'who': 'self'}] if exile else [])], None, optional)
