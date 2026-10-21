"""The graveyard counter watcher retains its native intervening condition and source UID."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('Whenever one or more +1/+1 counters are put on a creature you control, '
        'if this card is in your graveyard, you may put this card on top of your library.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text=TEXT.replace('put this card on top of your library',
                                                              'return this card to your hand')), ch)
    if native is None or native.get('effects') != [
        {'do': 'only_if', 'cond': {'object': 'self', 'test': 'in_graveyard'}, 'skip': 1},
        {'do': 'return_card', 'to': 'hand', 'who': 'self_gy'},
    ]:
        return None
    return {**native, 'effects': [native['effects'][0], {'do': 'to_library', 'who': 'self_gy', 'place': 'top'}]}
