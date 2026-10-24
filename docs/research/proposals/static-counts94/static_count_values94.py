"""Bounded count expressions for current static grants and characteristic definitions."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

_COLORS = {'white': 'W', 'blue': 'U', 'black': 'B', 'red': 'R', 'green': 'G'}


def _symbols(cost: str, color: str) -> int:
    # Each hybrid/Phyrexian symbol counts once for every color it contains.
    return sum(color in symbol.split('/') for symbol in re.findall(r'\{([^}]+)\}', cost))


def amount(plan: Plan, ctx: dict[str, Any], value: dict[str, Any]) -> int:
    from app.rules import selectors, values

    if 'quotient' in value:
        numerator, denominator = value['quotient']
        divisor = values.evaluate(plan, ctx, denominator)
        return values.evaluate(plan, ctx, numerator) // divisor if divisor > 0 else 0
    spec = value['mana_symbols']
    return sum(_symbols(plan.ch(plan.state.cards[cid]).mana_cost, spec['color'])
               for cid in selectors.candidates(plan, selectors.from_key(spec['among']), ctx['controller']))


def recipient(plan: Plan, card: CardInstance, value: dict[str, Any]) -> int:
    from app.rules.creature_types import CREATURE_TYPES

    current = plan.ch(card)
    if value['relative'] == 'mana_symbols':
        return _symbols(current.mana_cost, value['color'])
    return min(value['cap'], len(current.subtypes & CREATURE_TYPES))


def _each(text: str, value: dict[str, Any]) -> dict[str, Any]:
    from app.rules import statics

    native = statics.parse(text)
    assert native is not None and native.get('each') is not None
    return {**native, 'each': {**native['each'], 'value': value}}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors, statics, values

    if ability.kind != 'static':
        return None
    text = scripts.self_text(ability.text, ch.name)
    if (match := re.fullmatch(r'Each creature you control gets \+1/\+1 for each (?P<color>white|blue|black|red|green) mana symbol in its mana cost\.', text)) is not None:
        return _each('Each creature you control gets +1/+1 for each of its colors.',
                     {'relative': 'mana_symbols', 'color': _COLORS[match['color']]})
    if text == 'Each non-Human creature you control gets +1/+1 for each of its creature types, to a maximum of 10.':
        return _each('Each non-Human creature you control gets +1/+1 for each of its colors.',
                     {'relative': 'creature_types_count', 'cap': 10})
    if text == '~ gets +2/+0 for every seven cards in your graveyard.':
        count = values.parse_count('cards in your graveyard')
        assert count is not None
        return _each('~ gets +2/+0 for each card in your graveyard.', {'quotient': [count, 7]})
    if text == "~ gets -1/-1 for each card in your opponents' hands.":
        # Hand sizes are public; no hidden card identities or opponent-hand selectors are read.
        return _each('~ gets -1/-1 for each card in your hand.',
                     {'minus': [{'hand': 'all'}, {'hand': 'you'}]})
    if (match := re.fullmatch(r"~'s power and toughness are each equal to the number of (?P<color>white|blue|black|red|green) mana symbols in the mana costs of cards in your graveyard\.", text)) is not None:
        native = statics.parse("~'s power and toughness are each equal to the number of cards in your graveyard.")
        assert native is not None
        graveyard = selectors.Selector(zones=('graveyard',), zone_owner='you', card=True).key()
        value = {'mana_symbols': {'color': _COLORS[match['color']], 'among': graveyard}}
        return {**native, 'p': value, 't': value}
    return None
