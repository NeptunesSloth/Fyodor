"""Solving a Case is resolving its To solve ability, not manually changing a designation."""
from __future__ import annotations

from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import events, scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text != "When ~ enters and whenever you solve a Case, look at the top six cards of your library. You may reveal an enchantment card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.":
        return None
    enter = events.parse_condition('~ enters')
    assert enter is not None
    cond = {'event': 'either', 'conds': [enter, {'event': 'case_solved', 'subject': 'player', 'player': 'you'}]}
    sel = selectors.Selector(card=True, zones=('library',), types=('Enchantment',))
    return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'optional': False, 'target': None,
            'effects': [{'do': 'reveal_outcome_top', 'n': 6, 'player': 'you', 'exact_look': True},
                        {'do': 'pick_looked', 'n': 1, 'optional': True, 'sel': sel.key(), 'reveal': True, 'to': 'hand'},
                        {'do': 'rest_looked', 'to': 'bottom_random'}]}
