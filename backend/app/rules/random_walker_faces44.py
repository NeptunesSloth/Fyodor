"""Exact two-face native programs with object-aware conditional drawing."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

_FRONT = ('Whenever you cast an instant or sorcery spell during your turn, flip a coin. '
          'If you lose the flip, Ral deals 1 damage to you. If you win the flip, you may exile Ral. '
          "If you do, return him to the battlefield transformed under his owner's control.")
_ENTRY = "Ral enters with an additional loyalty counter on him for each instant and sorcery spell you've cast this turn."
_ULTIMATE = ('−8: Exile the top eight cards of your library. You may cast instant and sorcery spells '
             'from among them this turn without paying their mana costs.')
_DIVIDED = ('−2: Ral deals 2 damage divided as you choose among one or two targets. '
            'Draw a card if you control a blue permanent other than Ral.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text == _FRONT:
        native = scripts.define(replace(ability, text='Whenever you cast an instant or sorcery spell during your turn, flip a coin.'), ch)
        transform = scripts.parse_effects("You may exile ~. If you do, return it to the battlefield transformed under its owner's control.")
        if native is not None and transform is not None:
            return {**native, 'effects': [*native['effects'],
                    {'do': 'only_if', 'cond': {'coin': 'lose'}, 'skip': 1},
                    {'do': 'damage', 'who': 'you', 'n': 1},
                    {'do': 'only_if', 'cond': {'coin': 'win'}, 'skip': len(transform[0])}, *transform[0]]}
    if ability.text == _ENTRY:
        return scripts.define_replacement(ability,
            "~ enters with a number of loyalty counters on it equal to the number of instant and sorcery spells you've cast this turn.")
    if ability.text == _ULTIMATE:
        return scripts.define(replace(ability, text='−8: Exile the top eight cards of your library. Until end of turn, '
            'you may cast instant and sorcery spells from among those cards without paying their mana costs.'), ch)
    if ability.text == _DIVIDED:
        native = scripts.define(replace(ability, text='−2: Ral deals 2 damage divided as you choose among one or two targets.'), ch)
        if native is not None:
            return {**native, 'effects': [*native['effects'], {'do': 'ral_other_blue44'}]}
    return None


def draw_if_other_blue(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import coin_recipes

    source_oid = ctx.get('source_object')
    if source_oid and any(card.zone.endswith(':battlefield') and card.controller == ctx['controller']
                          and plan.oid(card) != source_oid and 'U' in plan.ch(card).colors
                          for card in plan.state.cards.values()):
        coin_recipes.insert(ctx, [{'do': 'draw', 'who': 'you', 'n': 1}])
    return True
