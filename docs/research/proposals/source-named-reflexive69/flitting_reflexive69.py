"""Mill first, then optional original-card exile before native reflexive target choice."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

_TEXT = 'When this creature dies, each player mills two cards. Then you may exile this card. When you do, put target creature or battle card from your graveyard on top of your library.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import context, scripts

    if ability.text.strip().casefold() not in (_TEXT.casefold(), _TEXT.replace('this creature', '~').replace('this card', '~').casefold()):
        return None
    native = scripts.define(replace(ability, text='When this creature dies, each player mills two cards.'), ch)
    tail = scripts.parse_effects('Put target creature or battle card from your graveyard on top of your library.')
    if native is None or tail is None:
        raise ValueError('Native Flitting death/reflexive shells unavailable')
    effects = [*native['effects'],
               {'do': 'only_if', 'cond': {'value': {'live_ref_count': context.EVENT_NEW, 'zone': 'graveyard'}, 'op': '>=', 'n': 1}, 'skip': 4},
               {'do': 'optional_payment', 'who': 'you', 'cost': '', 'ask': 'Exile this card', 'bind': 'flitting_accept69'},
               {'do': 'only_if', 'cond': {'succeeded': 'flitting_accept69'}, 'skip': 2},
               {'do': 'exile', 'who': context.EVENT_NEW, 'from_zone': 'graveyard', 'did': 'flitting_exiled69'},
               {'do': 'reflexive', 'cond': {'succeeded': 'flitting_exiled69'},
                'ability': {'kind': 'triggered', 'trigger': 'reflexive', 'effects': tail[0], 'optional': tail[2], **scripts.target_fields(tail[1])}}]
    return {**native, 'effects': effects, 'optional': False}
