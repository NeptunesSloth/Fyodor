"""Exact counter triggers filter the actual damage source and another player recipient."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TALON = ('Whenever a source you control other than ~ deals damage to an opponent, '
         'put a charge counter on ~.')
NIGHT = ('Whenever a source you control deals damage to another player, '
         'put that many theft counters on ~.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind != 'triggered' or text not in (TALON, NIGHT):
        return None
    native = (text.replace('other than ~ ', '') if text == TALON else
              text.replace('another player', 'an opponent'))
    found = scripts.define(replace(ability, text=native), ch)
    if found is None:
        return None
    if text == TALON:
        # Retain sources on the stack, public or hidden card zones, and the battlefield.
        source = selectors.Selector(zones=('battlefield', 'stack', 'graveyard', 'hand', 'library', 'exile', 'command'),
                                    controller='you', other=True)
        return {**found, 'cond': {'event': 'deal_damage', 'subject': 'sel', 'sel': source.key(),
                                 'to': 'opponent', 'min': 1}}
    # The existing recipient predicate is explicitly a player other than the ability controller.
    return found
