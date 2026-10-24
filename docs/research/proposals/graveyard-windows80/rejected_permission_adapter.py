"""Finite current graveyard objects receive the exact printed play or cast window."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

RECONSTRUCTION = ('At the beginning of your first main phase, mill a card, then exile a card from your graveyard '
                  'at random. You may play the exiled card this turn.')
CASE = ('Solved — Sacrifice this Case: Creature cards in your graveyard gain '
        '"You may cast this card from your graveyard" until end of turn.')


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.text == RECONSTRUCTION:
        native = scripts.define(replace(ability, text='At the beginning of your first main phase, you gain 1 life.'), ch)
        sel = selectors.Selector(zones=('graveyard',), zone_owner='you', card=True).key()
        return {**native, 'effects': [{'do': 'mill', 'who': 'you', 'n': 1},
                                     {'do': 'choose_random_object', 'sel': sel, 'as': 'reconstruction80_choice'},
                                     {'do': 'exile', 'who': 'ref:reconstruction80_choice', 'as': 'reconstruction80_exiled'},
                                     {'do': 'grant_play', 'who': 'ref:reconstruction80_exiled', 'from_exile': True,
                                      'play': True, 'cast': True, 'until': 'end_of_turn'}]} if native is not None else None
    if ability.text == CASE:
        native = scripts.define(replace(ability, text='Sacrifice this Case: You gain 1 life.'), ch)
        return {**native, 'effects': [{'do': 'case_graveyard_window80'}]} if native is not None else None
    return None


def case_window(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, permissions, selectors

    sel = selectors.Selector(zones=('graveyard',), zone_owner='you', card=True, types=('Creature',))
    found = selectors.candidates(plan, sel, ctx['controller'], ctx.get('source_card'))
    context.bind_objects(plan, ctx, 'case80_current_creatures', found)
    return permissions.grant_play(plan, ctx, {'who': 'ref:case80_current_creatures', 'play': False, 'cast': True,
                                               'until': 'end_of_turn'})


PRIMITIVES = {'case_graveyard_window80': case_window}
