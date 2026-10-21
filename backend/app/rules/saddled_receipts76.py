"""Exact Mount effects reuse native saddle designation and paid-contributor identities."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

MATRIX = '{2}, {T}: Target Mount you control becomes saddled until end of turn. Activate only as a sorcery.'
ARMORY = ('At the beginning of combat on your turn, choose up to one target Mount or Vehicle you control. '
          "Until end of turn, that permanent becomes saddled if it's a Mount and becomes an artifact creature if it's a Vehicle.")
POSSUM = ('Whenever this creature attacks while saddled, it gets +1/+2 until end of turn. '
          "Then you may return any number of creatures that saddled it this turn to their owner's hand.")
FELIDAR = ('Whenever this creature attacks while saddled, put a +1/+1 counter on each other creature you control. '
           'You gain 1 life for each of those creatures.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text == MATRIX and ability.kind == 'activated':
        base = scripts.define(replace(ability, text=MATRIX.replace('becomes saddled', 'gains vigilance')), ch)
        return {**base, 'effects': [{'do': 'saddle_it', 'who': 'target'}]} if base else None
    if ability.text == ARMORY and ability.kind == 'triggered':
        base = scripts.define(replace(ability, text='At the beginning of combat on your turn, up to one target Mount or Vehicle you control gains vigilance until end of turn.'), ch)
        return {**base, 'effects': [{'do': 'mount_vehicle76'}]} if base else None
    if ability.text in {POSSUM, FELIDAR} and ability.kind == 'triggered':
        base = scripts.define(replace(ability, text='Whenever this creature attacks while saddled, it gets +1/+2 until end of turn.'), ch)
        if base:
            return {**base, 'effects': [*base['effects'], {'do': 'saddle_contributors76'}] if ability.text == POSSUM else [{'do': 'mount_cohort76'}]}
    return None


def mount_vehicle(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import crew_saddle, effects

    for cid in effects._cards(plan, ctx, 'target:0'):
        c = plan.state.cards[cid]
        subtypes = plan.ch(c).subtypes
        if 'Mount' in subtypes:
            crew_saddle.became_saddled(plan, c)
        if 'Vehicle' in subtypes:
            effects.become(plan, ctx, {'who': 'target:0', 'types': ['Artifact', 'Creature'], 'retain': True, 'duration': 'end_of_turn'})
    return True


def contributors(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import crew_saddle, selectors

    # Original source OID is retained even when the Mount leaves or returns.
    keys = [selectors.Selector(types=('Creature',), extras=('oid:' + plan.oid(c),)).key()
            for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.in_game(c)
            and plan.ch(c).is_creature and crew_saddle.tapped_for(plan, 'saddle', plan.oid(c), ctx.get('source_object'))]
    if keys:
        ctx['effects'][ctx['next']:ctx['next']] = [
            {'do': 'player_chooses', 'who': 'you', 'sel': selectors.Selector(either=tuple(keys)).key(),
             'n': len(keys), 'upto': True, 'any': True, 'as': 'saddle_contributors76'},
            {'do': 'bounce', 'who': 'ref:saddle_contributors76'}]
    return True


def cohort(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    ids = [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.in_game(c)
           and c.controller == ctx['controller'] and plan.ch(c).is_creature and plan.oid(c) != ctx.get('source_object')]
    context.bind_objects(plan, ctx, 'mount_cohort76', ids)
    # Count the original cohort, including creatures prevented from receiving counters.
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do': 'add_counters', 'who': 'ref:mount_cohort76', 'kind': '+1/+1', 'n': 1},
        {'do': 'gain_life', 'who': 'you', 'n': len(ids)}]
    return True
