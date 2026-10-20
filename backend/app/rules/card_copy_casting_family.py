"""CR 707.12: typed sequences for selected or randomly linked card copies."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    body = ' '.join(body.split()).strip()
    if body.lower() == ('exile any number of target instant, sorcery, and/or tamiyo planeswalker cards from your graveyard. '
                        'copy them. you may cast any number of the copies.'):
        branches = [selectors.parse('instant or sorcery card in your graveyard'), selectors.parse('Tamiyo planeswalker card in your graveyard')]
        if any(s is None for s in branches):
            return None
        union = selectors.Selector(card=True, zones=('graveyard',), zone_owner='you',
                                   either=tuple(s.key() for s in branches if s is not None)).key()
        return ([{'do': 'exile', 'who': 'target:0', 'as': 'copy_originals'},
                 {'do': 'copy_cards', 'who': 'ref:copy_originals', 'as': 'card_copies'},
                 {'do': 'free_cast', 'zone': 'that', 'who': 'ref:card_copies', 'filter': None,
                  'optional': True, 'mv': None, 'n': 1, 'all': True, 'paid': True}],
                [{'what': union, 'min': 0, 'max': 250}], False)
    if body.lower().replace('~', 'this enchantment') == ('exile an instant or sorcery card at random from your graveyard. then copy each card exiled with this enchantment. '
                        'you may cast any number of the copies without paying their mana costs.'):
        parsed = scripts._parse_effects_plain('Choose an instant or sorcery card at random in your graveyard. Exile it. '
                                             'Copy each card exiled with ~. You may cast any number of the copies without paying their mana costs.')
        if parsed is None:
            return None
        found, target, optional = parsed
        found = [{**e, 'link': True} if e['do'] == 'exile' else
                 {**e, 'source_link': True} if e['do'] == 'copy_cards' and e.get('who') == 'exiled_with' else e for e in found]
        return found, target, optional
    return None
