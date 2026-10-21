"""Exact attack population values and a separately evaluated global Rat condition."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('Whenever this creature attacks, it gets +1/+0 until end of turn for each attacking creature. '
        'If a Rat is attacking, this creature gains trample until end of turn.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import conditions, scripts, selectors

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text='Whenever this creature attacks, it gets +1/+0 until end of turn.'), ch)
    rats = conditions.parse('there is an attacking Rat on the battlefield', objects=True)
    grant = scripts.parse_effects('This creature gains trample until end of turn.', ch.name)
    if native is None or rats is None or grant is None:
        return None
    effects = native.get('effects') or []
    if len(effects) != 1 or effects[0].get('do') != 'pump':
        return None
    count = selectors.Selector(types=('Creature',), attacking=True).key()
    return {**native, 'effects': [{**effects[0], 'p': {'count': count}},
                                  {'do': 'only_if', 'cond': rats, 'skip': 1}, *grant[0]]}
