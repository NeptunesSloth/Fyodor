"""Opt-in prepared battlefield cost events, with real replacement continuations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules import payment_continuations as pc
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules import mana as M
    from app.rules.plan import Plan


@dataclass
class CostEvent:
    kind: str
    objects: dict[str, str]
    text: str
    selector: str | None = None


@dataclass
class CostMoves:
    events: list[CostEvent]
    then: dict[str, Any]
    next: int = 0
    candidates: dict[str, list[dict[str, Any]]] | None = None
    chosen: dict[str, dict[str, Any]] = field(default_factory=dict)
    commanders: dict[str, bool] = field(default_factory=dict)
    riders: list[dict[str, Any]] = field(default_factory=list)


def continuation(plan: Plan, events: list[CostEvent], then: dict[str, Any]) -> dict[str, Any]:
    return pc.continuation(plan, 'cost_moves', CostMoves(events, then))



def _check(plan: Plan, event: CostEvent) -> None:
    from app.rules import prohibitions, selectors

    for cid, oid in event.objects.items():
        c = plan.state.cards.get(cid)
        if c is None or plan.oid(c) != oid or not c.zone.endswith(':battlefield') or c.controller != plan.actor or not plan.in_game(c):
            raise ActionError(f'The chosen permanent is no longer available to pay {event.text}')
        if event.selector and not selectors.matches(plan, selectors.from_key(event.selector), c, plan.ch(c), plan.actor, None):
            raise ActionError(f'That payment order cannot pay {event.text}; choose a different order or permanent')
        if event.kind == 'tap' and c.tapped:
            raise ActionError(f'Choose untapped creatures to pay {event.text}')
        if event.kind == 'sacrifice' and prohibitions.sacrifice_forbidden(plan, c):
            raise ActionError(f'{c.name} cannot be sacrificed')


def validate(plan: Plan, events: list[CostEvent]) -> None:
    from app.rules.plan import Plan

    probe = Plan(plan.state, plan.actor, plan.info, plan.rng)
    probe.rules.decision = None
    for event in events:
        _check(probe, event)
        if event.kind == 'tap':
            probe.do({'type': 'tap', 'card_ids': list(event.objects), 'tapped': True, 'cost': True})
        else:
            # All native replacements of these battlefield costs remove the same
            # original permanent. Project its departure before validating later
            # resources; replacement choices/riders run only on the real stage.
            dest = 'graveyard' if event.kind == 'sacrifice' else 'hand'
            probe.do({'type': 'move', 'card_ids': list(event.objects), 'to': {'zone': dest},
                      'routes': {cid: {'player': probe.state.cards[cid].owner, 'zone': dest} for cid in event.objects}})

def _run(plan: Plan, frame: CostMoves, payment: M.Payment | None) -> None:
    from app.rules import effects, replacements, triggers

    while True:
        held = plan.rules.declaration_cost_reserved
        if held and held.payer == plan.actor:
            held.objects = {cid: oid for event in frame.events[frame.next:] for cid, oid in event.objects.items()}
        if frame.riders:
            rider = frame.riders.pop(0)
            if rider.get('reflexive'):
                replacements.run_rider(plan, rider)
                continue
            source = plan.state.cards.get(rider['source'])
            ctx = {'controller': rider['controller'], 'source_card': rider['source'],
                   'source_object': rider['source_object'], 'name': rider['source_name'],
                   'targets': [], 'stack_id': '', 'kind': 'replacement', 'effects': rider['effects'],
                   'next': 0, 'x': None, 'event': None, 'body_done': pc.continuation(plan, 'cost_moves', frame)}
            # A replacement's effect is independent of its source surviving the cost.
            if source is None:
                ctx['source_card'] = None
            effects.continue_effects(plan, ctx)
            return
        if frame.next >= len(frame.events):
            plan.rules.declaration_cost_reserved = None
            pc.finish(plan, frame.then, payment)
            return
        event = frame.events[frame.next]
        ids = list(event.objects)
        _check(plan, event)
        if event.kind == 'tap':
            if any(plan.state.cards[cid].tapped for cid in ids):
                raise ActionError(f'Choose untapped creatures to pay {event.text}')
            plan.do({'type': 'tap', 'card_ids': ids, 'tapped': True, 'cost': True})
            frame.next += 1
            continue
        dest = 'graveyard' if event.kind == 'sacrifice' else 'hand'
        if frame.candidates is None:
            frame.candidates = {cid: [c._asdict() for c in replacements.zone_candidates(plan, plan.state.cards[cid], dest)] for cid in ids}
        # Every answer precedes the simultaneous event. No card moves early.
        for cid in ids:
            c = plan.state.cards[cid]
            candidates = {replacements.Cand(**raw).sig: raw for raw in frame.candidates[cid]}
            if candidates and cid not in frame.chosen:
                if len(candidates) == 1:
                    frame.chosen[cid] = next(iter(candidates.values()))
                else:
                    decide(plan, player=c.controller, kind='choose_one', prompt=f'{c.name}: choose the replacement for its cost payment',
                           options=[DecisionOption(id=key, label=raw['label']) for key, raw in candidates.items()],
                           min_choices=1, max_choices=1,
                           resume={'step': 'cost_moves', 'frame': pc.continuation(plan, 'cost_moves', frame), 'card': cid, 'stage': 'replacement', 'options': candidates}, source=c)
                    return
        for owner in plan.apnap():
            for cid in ids:
                c = plan.state.cards[cid]
                if dest != 'hand' or cid in frame.chosen or not c.commander_key or c.owner != owner or cid in frame.commanders:
                    continue
                from app.rules.engine import remembered
                answer = plan.rules.answers_903_9b.get(f'{plan.oid(c)}>hand') or remembered(plan, owner, f'commander_zone:{c.commander_key}', 'hand')
                if answer is not None:
                    frame.commanders[cid] = answer == 'yes'
                    continue
                decide(plan, player=owner, kind='choose_one', prompt=f'Return {c.name} to the command zone instead of your hand?',
                       options=[DecisionOption(id='yes', label='Command zone'), DecisionOption(id='no', label='Hand')], min_choices=1, max_choices=1,
                       resume={'step': 'cost_moves', 'frame': pc.continuation(plan, 'cost_moves', frame), 'card': cid, 'stage': 'commander'}, source=c)
                return
        routes, positions = {}, {}
        shuffle = set()
        marks: dict[str, list[str]] = {}
        links = []
        for cid in ids:
            c = plan.state.cards[cid]
            outcome = 'command' if frame.commanders.get(cid) else dest
            if cid in frame.chosen:
                cand = replacements.Cand(**frame.chosen[cid])
                outcome = cand.outcome
                if cand.used:
                    plan.rules.exile_if_graveyard = [x for x in plan.rules.exile_if_graveyard if x != event.objects[cid]]
                if cand.rider:
                    src = plan.state.cards.get(cand.rider['source'])
                    frame.riders.append({**cand.rider, 'source_object': plan.oid(src) if src else '', 'source_name': src.name if src else ''})
                if cand.link:
                    links.append((cid, cand))
                if cand.counter:
                    marks.setdefault(cand.counter, []).append(cid)
            if outcome.startswith('library:'):
                _, place = outcome.split(':', 1)
                outcome = 'library'
                positions[cid] = 'top' if place == 'shuffle' else place
                if place == 'shuffle':
                    shuffle.add(c.owner)
            routes[cid] = {'player': c.owner, 'zone': outcome}
        if event.kind == 'sacrifice':
            triggers.sacrificing(plan, ids)
        plan.rules.exile_if_leaves = [oid for oid in plan.rules.exile_if_leaves if oid not in event.objects.values()]
        payload: dict[str, Any] = {'type': 'move', 'card_ids': ids, 'to': {'zone': dest}, 'routes': routes}
        if dest == 'hand':
            payload['rest_zone'] = dest
        if positions:
            payload['library_positions'] = positions
        plan.do(payload)
        for cid, cand in links:
            replacements._record_link(plan, cid, cand)
        for kind, marked in marks.items():
            replacements.mark_exiled_counters(plan, marked, kind, actor=plan.actor)
        for owner in sorted(shuffle):
            plan.do({'type': 'shuffle', 'player': owner, 'zone': 'library'}, actor=owner)
        frame.next += 1
        frame.candidates = None
        frame.chosen = {}
        frame.commanders = {}


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from pydantic import TypeAdapter

    raw = d.resume
    frame = TypeAdapter(CostMoves).validate_python(raw['frame']['payload'])
    if raw['stage'] == 'replacement':
        frame.chosen[raw['card']] = raw['options'][chosen[0]]
    else:
        frame.commanders[raw['card']] = chosen[0] == 'yes'
    pc.finish(plan, {**raw['frame'], 'payload': TypeAdapter(CostMoves).dump_python(frame, mode='json')}, None)



def reserved(state: Any, player: str, cid: str) -> bool:
    r = state.rules
    held = r.declaration_cost_reserved if r is not None else None
    card = state.cards.get(cid)
    return bool(held and held.payer == player and player not in r.conceded and player not in r.lost
                and card and held.objects.get(cid) == r.object_id(cid))

pc.register('cost_moves', CostMoves, _run)
