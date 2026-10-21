"""Own graveyard positions are read from the original source incarnation."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

THREE = 'graveyard_three_creatures_above'
DIRECT = 'graveyard_creature_directly_above'
GY = {'object': 'self', 'test': 'in_graveyard'}

_RECIPES = {
    ('At the beginning of your upkeep, if this card is in your graveyard with three or more creature cards above it, '
     'you may put this card onto the battlefield.'): (
        'At the beginning of your upkeep, if this card is in your graveyard, '
        'you may return this card from your graveyard to the battlefield.', THREE),
    ('At the beginning of your upkeep, if this card is in your graveyard with a creature card directly above it, '
     'you may pay {1}. If you do, return this card to your hand.'): (
        'At the beginning of your upkeep, if this card is in your graveyard, '
        'you may pay {1}. If you do, return this card from your graveyard to your hand.', DIRECT),
    ('At the beginning of the end step, if this card is in your graveyard with a creature card directly above it, '
     'you may return this card to your hand.'): (
        'At the beginning of the end step, if this card is in your graveyard, '
        'you may return this card from your graveyard to your hand.', DIRECT),
}


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    text = ability.text.strip()
    recipe = _RECIPES.get(text) if ability.kind == 'triggered' else None
    if recipe is None:
        return None
    sentence, test = recipe
    native = scripts.define(replace(ability, text=sentence), ch)
    if native is None:
        return None
    guard = {'object': 'self', 'test': test}
    effects = [{**e, 'cond': guard} if e.get('do') == 'only_if' and e.get('cond') == GY else e
               for e in native['effects']]
    return {**native, 'if': guard, 'effects': effects}


def holds(plan: Plan, ctx: dict[str, Any], test: str) -> bool:
    card = plan.state.cards.get(ctx.get('source_card') or '')
    if card is None or card.zone != card.owner + ':graveyard' or plan.oid(card) != ctx.get('source_object'):
        return False
    yard = plan.state.zones.get(card.zone, [])
    if card.id not in yard:
        return False
    above = yard[yard.index(card.id) + 1:]
    if test == DIRECT:
        above = above[:1]
    count = sum(not plan.state.cards[c].is_token and plan.ch(plan.state.cards[c]).is_creature for c in above)
    return count >= (1 if test == DIRECT else 3)
