"""Exact artifact tap/activation watchers use immutable actual-cost facts."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import events, scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == ("Whenever an artifact an opponent controls becomes tapped or an opponent activates an artifact's ability "
                "without {T} in its activation cost, you gain 1 life."):
        tapped = events.parse_condition('an artifact an opponent controls becomes tapped')
        activated = events.parse_condition('an opponent activates an ability of an artifact')
        effects = [{'do': 'gain_life', 'who': 'you', 'n': 1}]
    elif text == ("Whenever an artifact becomes tapped or a player activates an artifact's ability without {T} in its "
                  "activation cost, ~ deals 1 damage to that artifact's controller."):
        tapped = events.parse_condition('an artifact becomes tapped')
        activated = events.parse_condition('a player activates an ability of an artifact')
        effects = [{'do': 'damage', 'who': 'ref:event.controller', 'n': 1}]
    elif text == ("Whenever enchanted artifact becomes tapped or a player activates an ability of enchanted artifact "
                  "without {T} in its activation cost, ~ deals 2 damage to that artifact's controller."):
        tapped = events.parse_condition('enchanted artifact becomes tapped')
        activated = {'event': 'activate', 'subject': 'host', 'nonmana': False, 'loyalty': False}
        effects = [{'do': 'damage', 'who': 'ref:event.controller', 'n': 2}]
    else:
        return None
    assert tapped is not None and activated is not None
    activated['activation_cost'] = {'has_tap': False}
    return {'kind': 'triggered', 'trigger': 'event',
            'cond': {'event': 'either', 'subject': 'mixed', 'conds': [tapped, activated]},
            'effects': effects, 'target': None, 'optional': False}
