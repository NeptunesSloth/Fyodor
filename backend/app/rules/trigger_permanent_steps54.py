"""Exact upkeep conditions use native distinct-type and count predicates at both checks."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

MASK = ("At the beginning of each player's upkeep, if there are four or more basic land types among lands "
        "that player controls, this artifact deals 3 damage to that player.")
ZEALOTS = 'At the beginning of your upkeep, if all nonland permanents you control are white, you gain 1 life.'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'triggered' or ability.text not in (MASK, ZEALOTS):
        return None
    from app.rules import scripts, selectors

    condition: dict[str, Any]
    if ability.text == MASK:
        base = "At the beginning of each player's upkeep, this artifact deals 3 damage to that player."
        lands = selectors.Selector(types=('Land',), controller='you')
        condition = {'as': 'event', 'cond': {'value': {'distinct': 'basic_land_types', 'among': lands.key()},
                                            'op': '>=', 'n': 4}}
    else:
        base = 'At the beginning of your upkeep, you gain 1 life.'
        nonwhite = selectors.Selector(not_types=('Land',), not_colors=('W',), controller='you')
        condition = {'value': {'count': nonwhite.key()}, 'op': '==', 'n': 0}
    native = scripts.define(replace(ability, text=base), ch)
    if native is None:
        return None
    return {**native, 'if': condition, 'effects': [
        {'do': 'only_if', 'cond': condition, 'skip': len(native['effects'])}, *native['effects']]}
