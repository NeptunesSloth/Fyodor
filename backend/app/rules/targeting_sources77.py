"""Targeting watches preserve native stack source identity and keyword provenance."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

HOJO = ('Whenever one or more creatures you control become the target of an activated ability, draw a card. '
        'This ability triggers only once each turn.')
LEYLINE = ('Whenever you and/or at least one permanent you control becomes the target of a spell or ability an opponent controls, '
           'this enchantment deals 2 damage to that player.')
HOPLITE = ('Whenever a creature you control becomes the target of a backup ability, copy that ability. '
           'You may choose new targets for the copy. This ability triggers only once each turn.')
BASE = 'Whenever a creature you control becomes the target of an ability, draw a card.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind != 'triggered':
        return None
    if ability.text in {HOJO, HOPLITE}:
        native = scripts.define(replace(ability, text=BASE), ch)
        if native is None:
            return None
        kind = 'activated' if ability.text == HOJO else 'backup'
        effects = native['effects'] if ability.text == HOJO else [{'do': 'copy_ability', 'who': 'event_ability'}, {'do': 'copy_new_targets'}]
        return {**native, 'limit': 'once_each_turn', 'effects': effects,
                'cond': {**native['cond'], 'aggregate': ability.text == HOJO, 'target_source77': kind}}
    if ability.text == LEYLINE:
        native = scripts.define(replace(ability, text='Whenever you become the target of a spell or ability an opponent controls, this enchantment deals 2 damage to that player.'), ch)
        if native is None:
            return None
        player = {**native['cond'], 'aggregate': True}
        permanent = {**player, 'subject': 'sel', 'sel': selectors.Selector(controller='you').key()}
        permanent.pop('player', None)
        return {**native, 'cond': {'event': 'either', 'conds': [player, permanent]},
                'effects': [{'do': 'targeting_actor_damage77'}]}
    return None


def matches(plan: Any, cond: dict[str, Any], fact: Any) -> bool:
    kind = cond.get('target_source77')
    if kind is None:
        return True
    ref = fact[4].get('source_ref')
    card = plan.state.cards.get(ref.card) if ref is not None else None
    if card is None or card.zone != 'stack' or plan.oid(card) != ref.object_id:
        return False
    entry = plan.rules.stack.get(card.id)
    if entry is None:
        return False
    if kind == 'activated':
        return entry.kind == 'activated'
    return kind == 'backup' and entry.kind == 'trigger' and card.stack_info is not None and 'Backup' in card.stack_info.tags


def damage_actor(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    actor = (ctx.get('event') or {}).get('actor')
    if not isinstance(actor, str) or actor not in plan.live():
        return True
    return effects.damage(plan, ctx, {'who': 'player:' + actor, 'n': 2})
