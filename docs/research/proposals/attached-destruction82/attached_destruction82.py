"""Attachment collateral uses the current host and native object destruction receipts."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    cases = {
        'Exile target attacking creature and all Equipment attached to it.': ('Exile target attacking creature.', 'exile'),
        'Destroy target creature with flying and all Equipment attached to that creature.': ('Destroy target creature with flying.', 'destroy'),
        '~ deals 6 damage to target creature. Destroy up to one Equipment attached to that creature.': ('~ deals 6 damage to target creature.', 'choose'),
        'Destroy target Equipment. If that Equipment was attached to a creature, ~ deals 2 damage to that creature.': ('Destroy target Equipment.', 'host'),
    }
    if text not in cases:
        return None
    proxy, mode = cases[text]
    native = scripts.define(replace(ability, text=proxy), ch)
    if native is None:
        return None
    seq: list[dict[str, Any]]
    if mode in ('destroy', 'exile'):
        seq = [{'do': 'attached_collateral82', 'action': mode}]
    elif mode == 'choose':
        seq = [*native['effects'], {'do': 'attached_choice82'}]
    else:
        seq = [{'do': 'attached_host82', 'as': 'attached82_host'}, *native['effects'], {'do': 'damage', 'who': 'ref:attached82_host', 'n': 2}]
    return {**native, 'effects': seq}


def collateral(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    hosts = effects._cards(plan, ctx, 'target')
    attached = [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield')
                and c.attached_to in hosts and 'Equipment' in plan.ch(c).subtypes]
    context.bind_objects(plan, ctx, 'attached82_union', [*hosts, *attached])
    action = effects.destroy if e['action'] == 'destroy' else effects.exile
    return action(plan, ctx, {'who': 'ref:attached82_union'})


def host(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    hosts = []
    for cid in effects._cards(plan, ctx, 'target'):
        h = plan.state.cards.get(plan.state.cards[cid].attached_to or '')
        if h is not None and h.zone.endswith(':battlefield') and 'Creature' in plan.ch(h).types:
            hosts.append(h.id)
    context.bind_objects(plan, ctx, e['as'], hosts)
    return True


def choose(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import choice_grants, context, effects

    hosts = effects._cards(plan, ctx, 'target')
    attached = [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield')
                and c.attached_to in hosts and 'Equipment' in plan.ch(c).subtypes]
    if not attached:
        return True
    context.bind_objects(plan, ctx, 'attached82_choices', attached)
    options: list[dict[str, Any]] = [{'label': 'Destroy no Equipment', 'effects': []}]
    for i, cid in enumerate(attached):
        key = f'attached82_choice{i}'
        context.bind_objects(plan, ctx, key, [cid])
        options.append({'label': 'Destroy ' + (plan.state.cards[cid].name or 'Equipment'),
                        'effects': [{'do': 'destroy', 'who': 'ref:' + key}]})
    return choice_grants.choose_effect(plan, ctx, {'who': 'ref:attached82_choices', 'options': options})


PRIMITIVES = {'attached_collateral82': collateral, 'attached_host82': host, 'attached_choice82': choose}
