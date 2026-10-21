"""Exact completed-draw receipts and ordinary random-target reflexives."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

_TEXT = ('Draw a card, then each other player may draw a card. Whenever a card is drawn this way, '
         'Explosion of Riches deals 5 damage to target opponent chosen at random from among your opponents.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text != _TEXT:
        return None
    from app.rules import scripts

    native = scripts.define(replace(ability, text='Draw a card.'), ch)
    lead = scripts.parse_effects('Draw a card. Each other player may draw a card.')
    if native is None or lead is None:
        return None
    return {**native, 'effects': [{'do': 'random_draw_reflexives43', 'kind': 'start'}, *lead[0],
                                {'do': 'random_draw_reflexives43', 'kind': 'finish'}]}


def consume(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import coin_recipes, this_way

    if effect['kind'] == 'start':
        this_way.mark_drawn(plan, ctx, 'r43_explosion_drawn')
    else:
        count = this_way.drawn(plan, ctx, {'ref_count': 'r43_explosion_drawn'})
        ability = {'kind': 'triggered', 'trigger': 'reflexive', 'effects': [{'do': 'damage', 'who': 'target', 'n': 5}],
                   'targets': [{'what': 'opponent', 'min': 1, 'max': 1, 'random': True}]}
        coin_recipes.insert(ctx, [{'do': 'reflexive', 'cond': {'all': []}, 'ability': ability} for _ in range(count)])
    return True
