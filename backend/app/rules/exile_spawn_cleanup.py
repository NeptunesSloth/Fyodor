"""Turn-long exile permission followed by remaining-card graveyard outcomes."""
from __future__ import annotations

from typing import Any

_TEXT = ('Exile the top three cards of your library. You may play those cards this turn. '
         'At the beginning of the next end step, if any of those cards remain exiled, put them into your graveyard, '
         'then create a 0/1 colorless Eldrazi Spawn creature token for each card put into your graveyard this way. '
         'Those tokens have "Sacrifice this token: Add {C}."')


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    if body.strip().casefold() != _TEXT.casefold():
        return None
    from app.rules import delayed, token_grammar

    tokens = token_grammar.parse('create a 0/1 colorless Eldrazi Spawn creature token with "Sacrifice this token: Add {C}."')
    assert tokens is not None
    condition = {'value': {'live_ref_count': 'spawn_exile', 'zone': 'exile'}, 'op': '>=', 'n': 1}
    cleanup: list[dict[str, Any]] = [{'do': 'only_if', 'cond': condition, 'skip': 2},
               {'do': 'return_card', 'who': 'ref:spawn_exile', 'to': 'graveyard', 'as': 'spawn_moved'},
               {**tokens[0], 'n': {'ref_count': 'spawn_moved', 'this_way': 'your_graveyard', 'of': None}}]
    return ([{'do': 'exile_top', 'n': 3, 'as': 'spawn_exile'},
             {'do': 'grant_play', 'who': 'ref:spawn_exile', 'play': True, 'cast': True,
              'until': 'end_of_turn', 'from_exile': True},
             *delayed.wrap_when(cleanup, {'kind': 'step', 'step': 'end', 'whose': 'next', 'if': condition})], None, False)
