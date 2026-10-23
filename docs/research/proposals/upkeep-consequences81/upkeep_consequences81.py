"""Bounded upkeep consequences use native destruction and opponent choices."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText

HORROR = 'At the beginning of your upkeep, destroy ~ unless you pay {3}{B}{B}{B}. If ~ is destroyed this way, it deals 7 damage to you.'
HORDES = "At the beginning of your upkeep, unless you pay {B}{B}{B}, tap ~ and sacrifice a land of an opponent's choice."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text == HORROR:
        return scripts.define(replace(ability, text='At the beginning of your upkeep, destroy ~ unless you pay {3}{B}{B}{B}. If that creature is destroyed this way, it deals 7 damage to you.'), ch)
    if text == HORDES:
        native = scripts.define(replace(ability, text='At the beginning of your upkeep, sacrifice ~ unless you pay {B}{B}{B}.'), ch)
        lands = selectors.parse('land you control')
        assert native is not None and lands is not None
        return {**native, 'effects': [
            {'do': 'optional_payment', 'who': 'you', 'cost': '{B}{B}{B}', 'bind': 'hordes81_paid'},
            {'do': 'only_if', 'cond': {'succeeded': 'hordes81_paid', 'negate': True}, 'skip': 4},
            {'do': 'tap', 'who': 'self'},
            {'do': 'choose_opponent', 'as': 'hordes81_opponent'},
            {'do': 'player_chooses', 'who': 'ref:hordes81_opponent', 'sel': lands.key(), 'n': 1, 'any': True, 'as': 'hordes81_land'},
            {'do': 'sacrifice', 'who': 'ref:hordes81_land'}]}
    return None
