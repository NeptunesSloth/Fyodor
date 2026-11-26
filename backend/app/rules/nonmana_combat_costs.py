"""Typed nonmana declaration fees, chosen before any payment commits."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import Decision, DecisionOption
from app.rules import cost_moves, cost_payment
from app.rules import costs as C
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

KIND = 'nonmana_declaration_cost'


@dataclass
class Part:
    component: C.CostComponent
    source: str
    label: str
    exclude: tuple[str, ...] = ()


def parse(text: str) -> dict[str, Any] | None:
    own = re.fullmatch(r"(?:~|[Tt]his creature) can't (?P<mode>attack or block|attack) unless you (?P<cost>sacrifice (?:two Islands|a land)|return an enchantment you control to its owner's hand|tap an untapped creature you control not declared as an attacking or blocking creature this combat)\.", text)
    if own:
        raw = own['cost']
        hollow = raw.startswith('tap ')
        native = 'tap an untapped creature you control' if hollow else raw
        cost = C.parse_additional_cost(native)
        if cost is None or len(cost.components) != 1:
            return None
        return {'kind': 'static', 'static': KIND, 'who': 'self', 'mode': own['mode'], 'cost': native, 'exclude_declared': hollow, 'effects': []}
    group = re.fullmatch(r"(?P<color>Green|Black) creatures can't attack unless their controller sacrifices a land of their choice for each (?:green|black) creature they control that's attacking\.", text)
    if group:
        return {'kind': 'static', 'static': KIND, 'who': 'global', 'mode': 'attack', 'cost': 'sacrifice a land', 'color': group['color'][0], 'effects': []}
    return None


def parts(plan: Plan, declared: set[str], mode: str) -> list[Part]:
    with plan.reading():  # -- big boards (Kiki end step) -- read-only: each permanent derived once
        return _parts(plan, declared, mode)


def _parts(plan: Plan, declared: set[str], mode: str) -> list[Part]:
    from dataclasses import replace

    from app.rules import scripts

    found = []
    for source in plan.state.cards.values():
        if not source.zone.endswith(':battlefield') or not plan.in_game(source):
            continue
        for definition in scripts.definitions(plan.ch(source)).values():
            if definition.get('static') != KIND or mode not in definition['mode']:
                continue
            if definition['who'] == 'self':
                amount = int(source.id in declared)
            else:
                amount = sum(definition['color'] in plan.ch(plan.state.cards[cid]).colors for cid in declared)
            if not amount:
                continue
            cost = C.parse_additional_cost(definition['cost'])
            assert cost is not None
            component = cost.components[0]
            excluded: tuple[str, ...] = ()
            if definition.get('exclude_declared'):
                from app.rules import history
                log = history.log_for(plan)
                excluded = tuple(declared | {c.id for c in plan.state.cards.values()
                    if log.declared.get(plan.oid(c)) == plan.rules.combats or log.declared_blockers.get(plan.oid(c)) == plan.rules.combats})
            found.append(Part(replace(component, amount=component.amount * amount), source.id, source.name or 'Creature', excluded))
    return found


def has_cost(plan: Plan, cid: str, mode: str) -> bool:
    return bool(parts(plan, {cid}, mode))


def prepare(plan: Plan, intent: A.DeclareAttackers | A.DeclareBlockers, declared: set[str], mode: str) -> list[cost_moves.CostEvent] | None:
    bundle = parts(plan, declared, mode)
    if not bundle:
        if intent.cost_choices or intent.cost_order:
            raise ActionError('This declaration has no additional cost to choose')
        return []
    original = plan.rules.decision
    assert original is not None
    cost = C.AbilityCost(components=tuple(p.component for p in bundle))
    source = plan.state.cards[bundle[0].source]
    for part in bundle:
        before = plan.excluded
        plan.excluded = before | set(part.exclude)
        previous = plan.resolution_cost
        plan.resolution_cost = True  # Declaration fees are not casting/activation costs.
        try:
            problem = cost_payment.problem(plan, C.AbilityCost(components=(part.component,)), source, plan.actor)
        finally:
            plan.excluded = before
            plan.resolution_cost = previous
        if problem:
            raise ActionError(problem)
    previous = plan.resolution_cost
    plan.resolution_cost = True
    try:
        chosen = cost_payment.choose(plan, intent, cost, source, 'Declare creatures',
                                     compatible_tap=True, component_excluded={i: set(p.exclude) for i,p in enumerate(bundle)})
    finally:
        plan.resolution_cost = previous
    if chosen is None:
        assert plan.rules.decision and plan.rules.decision.resume is not None
        plan.rules.decision.resume['declaration_decision'] = original.model_dump(mode='json')
        return None
    if not intent.cost_order and len(bundle) > 1:
        decide(plan, player=plan.actor, kind='order', prompt='Choose the order to pay these declaration costs',
               options=[DecisionOption(id=str(i), label=f'{p.label}: {p.component.text}') for i,p in enumerate(bundle)],
               min_choices=len(bundle), max_choices=len(bundle),
               resume={'step': 'declaration_cost_order', 'intent': intent.model_dump(mode='json', exclude={'actor','ts','r'}),
                       'declaration_decision': original.model_dump(mode='json')})
        # Preserve auto-chosen objects while only choosing the payment order.
        decision = plan.rules.decision
        assert decision is not None and decision.resume is not None
        decision.resume['intent']['cost_choices'] = [{'component': i, 'cards': ids} for i,ids in chosen.items()]
        return None
    order = intent.cost_order or [0]
    if len(order) != len(bundle) or set(order) != set(range(len(bundle))):
        raise ActionError('Choose every declaration cost once')
    paid: dict[str, str] = {}
    events = []
    for i in order:
        part, ids = bundle[i], chosen[i]
        kind = {C.TAP_OTHER: 'tap', C.SACRIFICE: 'sacrifice', C.RETURN_PERMANENT: 'return'}[part.component.kind]
        for cid in ids:
            if cid in paid and not (paid[cid] == 'tap' and kind in ('sacrifice','return')):
                raise ActionError('Tap a permanent before sacrificing or returning it; one action cannot pay two costs')
            paid[cid] = kind
        events.append(cost_moves.CostEvent(kind, {cid: plan.oid(plan.state.cards[cid]) for cid in ids}, part.component.text, part.component.selector))
    cost_moves.validate(plan, events)
    return events


def after(plan: Plan, events: list[cost_moves.CostEvent], then: dict[str, Any]) -> dict[str, Any]:
    return cost_moves.continuation(plan, events, then) if events else then


def resume_order(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.engine import INTENTS

    intent = A.parse_action(d.resume['intent'])
    assert isinstance(intent, A.DeclareAttackers | A.DeclareBlockers)
    intent.cost_order = [int(i) for i in chosen]
    plan.rules.decision = Decision.model_validate(d.resume['declaration_decision'])
    INTENTS[intent.type](plan, intent)
