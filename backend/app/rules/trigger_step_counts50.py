"""Bound step-player quantities without changing the ability's controller."""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

TEXT = ("At the beginning of each player's first main phase, if this artifact is untapped, "
        "that player adds {C} for each artifact they control.")
VISIONS_TEXT = ("At the beginning of each player's end step, that player draws a card. "
                "If the player is your opponent and has four or more cards in hand, "
                "this enchantment deals 2 damage to that player.")
VISIONS_BASE = "At the beginning of each player's end step, that player draws a card."

BASE = ("At the beginning of each player's first main phase, if this artifact is untapped, "
        "that player adds {C}.")


ADMITTED_TEXTS = frozenset({VISIONS_TEXT})


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'triggered' or ability.text not in ADMITTED_TEXTS:
        return None
    from app.rules import scripts, selectors

    native = scripts.define(replace(ability, text=BASE if ability.text == TEXT else VISIONS_BASE), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    effects = out.get('effects') or []
    if ability.text == VISIONS_TEXT:
        out['effects'] = [*effects, {'do': 'only_if', 'cond': {'all': [
            {'event_player_relation': 'opponent'},
            {'as': 'event', 'cond': {'value': {'hand': 'you'}, 'op': '>=', 'n': 4}}]}, 'skip': 1},
            {'do': 'damage', 'who': 'event_player', 'n': 2}]
        return out
    produced = [e for e in effects if e.get('do') == 'add_mana']
    if len(produced) != 1 or produced[0].get('who') != 'event_player':
        return None
    effect = produced[0]
    effect.pop('mana', None)
    effect.update(sym='C', n={'for_player': 'event', 'of': {
        'count': selectors.Selector(types=('Artifact',), controller='you').key()}})
    return out
