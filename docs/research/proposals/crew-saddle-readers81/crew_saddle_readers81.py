"""Exact crew/saddle readers retain native object identities and graveyard grants."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

SCHOONER = 'Whenever this Vehicle attacks, target creature that crewed it this turn explores.'
GHOST = 'Repair Barge — Whenever this Vehicle becomes crewed, each artifact creature card in your graveyard gains unearth {3} until end of turn.'
NEWT = ('Whenever this creature deals combat damage to a player, target instant or sorcery card in your graveyard gains flashback until end of turn. '
        'The flashback cost is equal to its mana cost. That card gains flashback {0} until end of turn instead if this creature is saddled.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered':
        return None
    if ability.text == SCHOONER:
        native = scripts.define(replace(ability, text=SCHOONER.replace('explores.', 'gains vigilance until end of turn.')), ch)
        return {**native, 'effects': [{'do': 'explore', 'who': 'target'}]} if native else None
    if ability.text == GHOST:
        native = scripts.define(replace(ability, text='Whenever this Vehicle becomes crewed, draw a card.'), ch)
        return {**native, 'effects': [{'do': 'ghost_unearth81'}]} if native else None
    if ability.text == NEWT:
        native = scripts.define(replace(ability, text=NEWT.split(' That card gains')[0]), ch)
        return {**native, 'effects': [{'do': 'newt_flashback81'}]} if native else None
    return None


def bound_target(sel: Any, source_object: str) -> Any:
    from app.rules import selectors

    extras = tuple('paid_contributor81:' + ('crew' if x == 'crewed_it' else 'saddle') + ':' + source_object
                   if x in {'crewed_it', 'saddled_it'} else x for x in sel.extras)
    either = tuple(bound_target(selectors.from_key(key), source_object).key() for key in sel.either)
    return replace(sel, extras=extras, either=either) if extras != sel.extras or either != sel.either else sel


def ghost_unearth(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import effects, layers, selectors

    selector = selectors.parse('artifact creature cards in your graveyard')
    assert selector is not None
    for cid in effects._cards(plan, ctx, selector.key()):
        layers.add_effect(plan, affected=[plan.oid(cid)], layer='6', source=ctx.get('source_object'),
            controller=ctx['controller'], duration='end_of_turn', add_abilities=['Unearth {3}.'],
            ability_zone='graveyard', label='Unearth {3} until end of turn')
    return True


def newt_flashback(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import graveyard_grants

    log = plan.rules.turn_log
    # An ability uses its original source's last known designation after it leaves,
    # never a new incarnation of the physical card. Saddle facts predate this card.
    saddled = log.turn == plan.state.turn.number and any(
        f.kind == 'saddled' and f.object_id == ctx.get('source_object') for f in log.facts)
    return graveyard_grants.grant_flashback(plan, ctx, {'who': 'target', 'cost': '{0}' if saddled else 'mana_cost'})


PRIMITIVES = {'ghost_unearth81': ghost_unearth, 'newt_flashback81': newt_flashback}
