"""Isolated lazy native frontier prefixes; no chooser, planner or commit hook.

Each transition reuses native applicability/application with an independent local
budget. Global entitlement remains the joint constraint model's responsibility;
these provisional prefixes must never spend budgets in packet traversal order.
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan
    from app.rules.replace import Candidate


@dataclass(frozen=True)
class Leaf:
    id: str
    event: str
    chooser: str


@dataclass(frozen=True)
class Pick:
    leaf: str
    candidate: str
    amount: int | None
    order_player: str = ''
    allocation_player: str = ''


@dataclass(frozen=True)
class Pending:
    leaf: str
    candidate: str
    order_player: str
    allocation_player: str


@dataclass(frozen=True)
class Draft:
    candidates: str
    originals: str
    leaves: tuple[Leaf, ...]
    picks: tuple[Pick, ...] = ()
    pending: Pending | None = None

    def dumps(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def loads(cls, text: str) -> Draft:
        data = json.loads(text)
        return cls(data['candidates'], data['originals'], tuple(Leaf(**x) for x in data['leaves']),
                   tuple(Pick(**x) for x in data['picks']),
                   Pending(**data['pending']) if data.get('pending') is not None else None)


def _candidates(plan: Plan, draft: Draft | None = None) -> list[Candidate]:
    from app.rules import prevention_frontier_grounding as grounding
    from app.rules import replace

    candidates = replace.damage_candidates(plan)
    if draft is not None and grounding._canonical(candidates) != draft.candidates:
        raise ValueError('Native frontier candidates changed')
    return candidates


def _event(plan: Plan, leaf: Leaf) -> dict[str, Any]:
    from app.rules import replace

    event: dict[str, Any] = json.loads(leaf.event)
    target = event['target']
    oid = plan.oid(target) if target in plan.state.cards else None
    if event.get('target_oid') != oid or replace.affected(plan, event) != leaf.chooser:
        raise ValueError('Native frontier recipient incarnation or controller changed')
    return event


def _chooser(plan: Plan, event: dict[str, Any]) -> str:
    from app.rules import replace

    chooser = replace.affected(plan, event)
    if chooser is None:
        raise ValueError('Native frontier recipient has no affected player')
    return chooser


def _sim(plan: Plan) -> dict[str, Any]:
    return {'shields': {k: int(v) for k, v in plan.rules.prevention.items()}, 'redirect_allocations': {}}


def start(plan: Plan, events: list[dict[str, Any]]) -> Draft:
    from app.rules import prevention_frontier_grounding as grounding
    from app.rules import source_shields

    originals = copy.deepcopy(events)
    leaves = []
    seen = set()
    for index, event in enumerate(originals):
        if not event.get('source_oid'):
            raise ValueError('Native frontier needs the original source OID')
        lineage = str(event.setdefault('_damage_lineage', str(index)))
        if lineage in seen:
            raise ValueError('Native frontier original lineages must be unique')
        seen.add(lineage)
        event.setdefault('_redirect_lineage', lineage)
        event['kind'] = 'damage'
        event.setdefault('applied', [])
        event.setdefault('prevented', 0)
        event['target_oid'] = plan.oid(event['target']) if event['target'] in plan.state.cards else None
        if source_shields.unpreventable(plan, event):
            event['unpreventable'] = True
        leaves.append(Leaf(lineage, json.dumps(event, sort_keys=True), _chooser(plan, event)))
    return Draft(grounding._canonical(_candidates(plan)), json.dumps(originals, sort_keys=True), tuple(leaves))


def choices(plan: Plan, draft: Draft, leaf_id: str) -> tuple[Candidate, ...]:
    from app.rules import prevention_frontier_grounding as grounding
    from app.rules import replace

    candidates = _candidates(plan, draft)
    leaf = next(x for x in draft.leaves if x.id == leaf_id)
    event = _event(plan, leaf)
    planner = replace.Planner(plan, candidates, ask=False)
    sim = _sim(plan)
    # Native optional() runs before applicable(); never silently omit it.
    for candidate in candidates:
        if planner.applies(candidate, event, sim):
            grounding._supported(candidate)
    available = planner.applicable(event, sim)
    return tuple(available)


def advance(plan: Plan, draft: Draft, leaf_id: str, candidate_id: str, *, amount: int | None = None) -> Draft:
    """One trusted provisional local choice; never a whole-order permutation list."""
    from app.rules import replace, single_recipient_redirection

    untouched = plan.state.model_dump_json()
    by_id = {c.id: c for c in choices(plan, draft, leaf_id)}
    if candidate_id not in by_id:
        raise ValueError('Candidate is not a legal native local choice')
    candidate = by_id[candidate_id]
    leaf = next(x for x in draft.leaves if x.id == leaf_id)
    event = _event(plan, leaf)
    sim = _sim(plan)
    finite = candidate.op['do'] in ('finite_prevention', 'redirect')
    if finite:
        limit = min(int(event['amount']), int(candidate.op['limit']))
        if amount is None or isinstance(amount, bool) or amount < 0 or amount > limit:
            raise ValueError('A finite provisional row needs an exact legal numeric allocation')
        identity = single_recipient_redirection.identity(candidate, event)
        row = str(event['_redirect_lineage']) + ':' + ','.join(event.get('applied') or [])
        sim['redirect_allocations'][identity] = {row: amount}
    elif amount is not None:
        raise ValueError('Only a finite pool has a numeric allocation')
    planner = replace.Planner(plan, _candidates(plan, draft), ask=False)
    children = planner.apply(candidate, copy.deepcopy(event), sim)
    new_leaves = []
    for index, child in enumerate(children):
        if child['amount'] <= 0:
            continue
        moved = candidate.op['do'] == 'redirect' and bool(amount) and index == 0
        branch = (json.dumps([leaf_id, candidate_id, child['target'], child.get('target_oid') or ''], separators=(',', ':'))
                  if moved else leaf_id)
        child['_redirect_lineage'] = branch
        new_leaves.append(Leaf(branch, json.dumps(child, sort_keys=True), _chooser(plan, child)))
    out = tuple(x for x in draft.leaves if x.id != leaf_id) + tuple(new_leaves)
    if plan.state.model_dump_json() != untouched:
        raise AssertionError('Native frontier discovery mutated game state')
    return Draft(draft.candidates, draft.originals, out, draft.picks +
                 (Pick(leaf_id, candidate_id, amount, leaf.chooser, candidate.controller if finite else ''),))


def choose_order(plan: Plan, draft: Draft, leaf_id: str, candidate_id: str, actor: str) -> Draft:
    from dataclasses import replace as changed

    if draft.pending is not None:
        raise ValueError('The selected native order is awaiting its separate pool owner')
    leaf = next(x for x in draft.leaves if x.id == leaf_id)
    if actor != leaf.chooser:
        raise ValueError('Only the affected player chooses this native replacement order')
    candidate = next((c for c in choices(plan, draft, leaf_id) if c.id == candidate_id), None)
    if candidate is None:
        raise ValueError('Candidate is not a legal native local choice')
    if candidate.op['do'] not in ('finite_prevention', 'redirect'):
        return advance(plan, draft, leaf_id, candidate_id)
    return changed(draft, pending=Pending(leaf_id, candidate_id, leaf.chooser, candidate.controller))


def choose_amount(plan: Plan, draft: Draft, amount: int, actor: str) -> Draft:
    pending = draft.pending
    if pending is None:
        raise ValueError('There is no selected native finite pool')
    if actor != pending.allocation_player:
        raise ValueError('Only the pool controller chooses its global allocation row')
    candidate = next((c for c in choices(plan, draft, pending.leaf) if c.id == pending.candidate), None)
    leaf = next(x for x in draft.leaves if x.id == pending.leaf)
    if candidate is None or candidate.controller != pending.allocation_player or leaf.chooser != pending.order_player:
        raise ValueError('Native order or pool ownership changed')
    return advance(plan, draft, pending.leaf, pending.candidate, amount=amount)
