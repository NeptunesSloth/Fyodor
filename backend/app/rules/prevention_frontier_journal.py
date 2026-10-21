"""Unregistered native question/reset journal; no engine chooser or commit hook."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from dataclasses import replace as changed
from typing import TYPE_CHECKING, Any, Literal

from app.rules import prevention_frontier_constraints as affine
from app.rules import prevention_frontier_discovery as lazy
from app.rules import prevention_frontier_joint_draft as joint
from app.rules import prevention_frontier_symbolic as symbolic

if TYPE_CHECKING:
    from app.rules.plan import Plan


@dataclass(frozen=True)
class Number:
    group: str
    row: str
    amount: int
    owner: str


@dataclass(frozen=True)
class Frame:
    batch: str
    events: str
    candidates: str
    subjects: tuple[tuple[str, str, str], ...]
    orders: tuple[symbolic.Order, ...] = ()
    numeric: tuple[Number, ...] = ()

    def dumps(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def loads(cls, text: str) -> Frame:
        data = json.loads(text)
        return cls(data['batch'], data['events'], data['candidates'], tuple(tuple(x) for x in data['subjects']),
                   tuple(symbolic.Order(x['key'], x['chooser'], tuple(x['candidates']), x['selected']) for x in data['orders']),
                   tuple(Number(**x) for x in data['numeric']))


@dataclass(frozen=True)
class Question:
    kind: Literal['order', 'amount']
    actor: str
    leaf: str
    key: str
    candidates: tuple[str, ...]
    candidate: str = ''
    group: str = ''
    maximum: int = 0


def start(plan: Plan, events: list[dict[str, Any]], *, batch: str) -> Frame:
    draft = lazy.start(plan, events)
    subjects = tuple((event['target'], event.get('target_oid') or '', lazy._chooser(plan, event))
                     for event in json.loads(draft.originals))
    return Frame(batch, draft.originals, draft.candidates, subjects)


def _validate(plan: Plan, frame: Frame) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = json.loads(frame.events)
    current = start(plan, events, batch=frame.batch)
    if current.candidates != frame.candidates or current.events != frame.events or current.subjects != frame.subjects:
        raise ValueError('The saved native joint snapshot is stale')
    if len({o.key for o in frame.orders}) != len(frame.orders) or len({(n.group, n.row) for n in frame.numeric}) != len(frame.numeric):
        raise ValueError('Ambiguous saved native joint prefixes')
    return events


def _witness(plan: Plan, frame: Frame) -> symbolic.Completion | None:
    return symbolic.witness(plan, json.loads(frame.events), batch=frame.batch, orders=frame.orders,
                            numeric=tuple((n.group, n.row, n.amount) for n in frame.numeric))


def question(plan: Plan, frame: Frame) -> Question | joint.Completed:
    """Replay only actual confirmed prefixes; never ask on an invented future branch."""
    events = _validate(plan, frame)
    draft = lazy.start(plan, events)
    orders = {o.key: o for o in frame.orders}
    numbers = {(n.group, n.row): n for n in frame.numeric}
    apnap = plan.apnap()
    while True:
        progressed = False
        leaves = sorted(draft.leaves, key=lambda x: (apnap.index(x.chooser) if x.chooser in apnap else len(apnap), x.id))
        for leaf in leaves:
            candidates = lazy.choices(plan, draft, leaf.id)
            if not candidates:
                continue
            event = lazy._event(plan, leaf)
            key = symbolic.order_key(event, leaf.id)
            ids = tuple(c.id for c in candidates)
            saved = orders.get(key)
            if saved is not None and (saved.chooser != leaf.chooser or saved.candidates != ids or saved.selected not in ids):
                raise ValueError('The saved affected-player order is stale')
            if len(candidates) > 1 and saved is None:
                return Question('order', leaf.chooser, leaf.id, key, ids)
            candidate = next(c for c in candidates if c.id == saved.selected) if saved else candidates[0]
            if candidate.op['do'] in ('finite_prevention', 'redirect'):
                group = json.dumps([candidate.id, frame.batch, event['source_oid'] if candidate.op.get('budget_scope') == 'source_batch' else None],
                                   separators=(',', ':'))
                numeric = numbers.get((group, leaf.id))
                if numeric is None:
                    return Question('amount', candidate.controller, leaf.id, key, ids, candidate.id, group,
                                    min(int(event['amount']), int(candidate.op['limit'])))
                if numeric.owner != candidate.controller:
                    raise ValueError('The saved numeric prefix has forged pool ownership')
                draft = lazy.advance(plan, draft, leaf.id, candidate.id, amount=numeric.amount)
            else:
                draft = lazy.advance(plan, draft, leaf.id, candidate.id)
            progressed = True
            break
        if not progressed:
            return joint.complete(plan, draft, batch=frame.batch)


Signature = tuple[tuple[tuple[affine.Variable, tuple[int, int]], ...],
                  tuple[tuple[int, tuple[tuple[affine.Variable, int], ...]], ...]]


def _signatures(layout: symbolic.Layout) -> tuple[dict[str, Signature], dict[str, set[str]]]:
    bounds, constraints, cases = affine.model(layout.frontier, layout.zero_terminals)
    expressions = [*constraints, *(expression for case in cases for expression in case)]
    groups = {key[0] for key in bounds}
    signatures = {}
    graph: dict[str, set[str]] = {group: set() for group in groups}
    for group in groups:
        signatures[group] = (tuple(sorted((key, bound) for key, bound in bounds.items() if key[0] == group)),
                             tuple(sorted((e.constant, e.terms) for e in expressions if any(key[0] == group for key, _ in e.terms))))
    for expression in expressions:
        connected = {key[0] for key, _ in expression.terms}
        for group in connected:
            graph[group].update(connected - {group})
    return signatures, graph


def choose_order(plan: Plan, frame: Frame, candidate: str, actor: str) -> Frame:
    q = question(plan, frame)
    if not isinstance(q, Question) or q.kind != 'order':
        raise ValueError('There is no pending native replacement order')
    if actor != q.actor or candidate not in q.candidates:
        raise ValueError('Only the affected player chooses a legal native replacement order')
    answer = symbolic.Order(q.key, q.actor, q.candidates, candidate)
    proposed = changed(frame, orders=(*tuple(o for o in frame.orders if o.key != q.key), answer))
    if _witness(plan, proposed) is not None:
        return proposed
    old = _witness(plan, frame)
    new = _witness(plan, changed(proposed, numeric=()))
    if old is None or new is None:
        raise ValueError('The selected native order has no supported joint completion')
    before, old_graph = _signatures(old.layout)
    after, new_graph = _signatures(new.layout)
    dirty = {group for group in before.keys() | after.keys() if before.get(group) != after.get(group)}
    while True:
        related = {other for group in dirty for other in old_graph.get(group, set()) | new_graph.get(group, set())}
        if related <= dirty:
            break
        dirty |= related
    proposed = changed(proposed, numeric=tuple(n for n in proposed.numeric if n.group not in dirty))
    if _witness(plan, proposed) is None:
        raise ValueError('The native dependency reset has no supported joint completion')
    return proposed


def choose_amount(plan: Plan, frame: Frame, amount: int, actor: str) -> Frame:
    q = question(plan, frame)
    if not isinstance(q, Question) or q.kind != 'amount':
        raise ValueError('There is no pending native numeric allocation')
    if actor != q.actor:
        raise ValueError('Only the pool controller chooses its native numeric allocation')
    if isinstance(amount, bool) or amount < 0 or amount > q.maximum:
        raise ValueError('The native numeric allocation is outside its actual capacity')
    answer = Number(q.group, q.leaf, amount, q.actor)
    proposed = changed(frame, numeric=(*tuple(n for n in frame.numeric if (n.group, n.row) != (q.group, q.leaf)), answer))
    if _witness(plan, proposed) is None:
        raise ValueError('The native numeric allocation has no jointly feasible completion')
    return proposed
