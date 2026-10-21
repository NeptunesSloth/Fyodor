"""Unregistered lazy symbolic native order completion; no questions or commit.

Whole order permutations are never materialized. Each candidate prefix extends
on demand, and affine integer feasibility supplies allocations without damage-
amount enumeration. Unsupported positive frontiers are never silently omitted.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.rules import prevention_frontier_constraints as affine
from app.rules import prevention_frontier_discovery as lazy
from app.rules import prevention_frontier_grounding as native
from app.rules import prevention_frontier_prototype as model

if TYPE_CHECKING:
    from app.rules.plan import Plan


@dataclass(frozen=True)
class Order:
    key: str
    chooser: str
    candidates: tuple[str, ...]
    selected: str


@dataclass(frozen=True)
class Part:
    operations: tuple[model.Operation, ...] = ()
    traces: tuple[model.LocalTrace, ...] = ()
    pools: tuple[model.Pool, ...] = ()
    orders: tuple[Order, ...] = ()
    zero_terminals: tuple[str, ...] = ()


@dataclass(frozen=True)
class Layout:
    frontier: model.Frontier
    orders: tuple[Order, ...]
    zero_terminals: tuple[str, ...]


@dataclass(frozen=True)
class Completion:
    layout: Layout
    solution: model.Solution
    grounded: native.Grounded


def order_key(event: dict[str, Any], path: str) -> str:
    return json.dumps([event['source_oid'], path, event['target'], event.get('target_oid') or '',
                       sorted(event.get('applied') or [])], separators=(',', ':'))


def _merge_pools(pools: tuple[model.Pool, ...]) -> tuple[model.Pool, ...]:
    by_id: dict[str, model.Pool] = {}
    for pool in pools:
        if pool.id in by_id and by_id[pool.id] != pool:
            raise ValueError('A shared native pool has source-dependent destinations or ownership')
        by_id[pool.id] = pool
    return tuple(by_id.values())


def layouts(plan: Plan, events: list[dict[str, Any]], *, batch: str,
            orders: tuple[Order, ...] = ()) -> Iterator[Layout]:
    from app.rules import replace, source_shields

    originals = json.loads(lazy.start(plan, events).originals)
    candidates = replace.damage_candidates(plan)
    planner = replace.Planner(plan, candidates, ask=False)
    selected = {}
    for order in orders:
        if order.key in selected:
            raise ValueError('Ambiguous saved native order prefix')
        selected[order.key] = order

    def walk(event: dict[str, Any], path: str) -> Iterator[Part]:
        if int(event['amount']) <= 0:
            yield Part()
            return
        sim = lazy._sim(plan)
        available = planner.applicable(event, sim)
        # Optional choices run before ordinary applicable() in the native planner.
        if any(c.op.get('optional') and not c.op.get('external_optional') and planner.applies(c, event, sim) for c in candidates):
            yield Part(zero_terminals=(path,))
            return
        if not available:
            yield Part()
            return
        key = order_key(event, path)
        wanted = selected.get(key)
        chooser = lazy._chooser(plan, event)
        if wanted is not None and (wanted.chooser != chooser or wanted.candidates != tuple(c.id for c in available)):
            raise ValueError('The saved native order chooser or candidate set changed')
        unsupported = False
        for candidate in available:
            try:
                native._supported(candidate)
            except ValueError:
                unsupported = True
                continue
            if wanted is not None and wanted.selected != candidate.id:
                continue
            stamp = Order(key, chooser, tuple(c.id for c in available), candidate.id)
            current = copy.deepcopy(event)
            current['applied'] = [*(event.get('applied') or []), candidate.id]
            op = candidate.op
            kind = op['do']
            pool = None
            child = None
            child_path = ''
            if kind == 'mul':
                operation = model.Operation(candidate.id, 'multiply', factor=int(op['n']))
                current['amount'] *= int(op['n'])
            elif kind == 'prevent_all':
                operation = model.Operation(candidate.id, 'protection')
                if not current.get('unpreventable'):
                    current['amount'] = 0
            else:
                operation = model.Operation(candidate.id, 'pool', pool=candidate.id)
                target, oid, affected = '', '', ''
                if kind == 'redirect':
                    target = source_shields.redirect_target(plan, candidate, current) or ''
                    if not target:
                        raise ValueError('Native redirect destination changed')
                    oid = plan.oid(target) if target in plan.state.cards else ''
                    child = {**current, 'target': target, 'target_oid': oid or None,
                             'amount': min(int(current['amount']), int(op['limit']))}
                    affected = lazy._chooser(plan, child)
                    child_path = json.dumps([path, candidate.id, target, oid], separators=(',', ':'))
                    child['_redirect_lineage'] = child_path
                pool = model.Pool(candidate.id, candidate.controller, int(op['limit']),
                                  scope='source_batch' if op.get('budget_scope') == 'source_batch' else 'turn',
                                  mode='redirect' if kind == 'redirect' else 'prevent',
                                  destination=target, destination_oid=oid, destination_controller=affected)
            for children in walk(child, child_path) if child is not None else (Part(),):
                trace = ((model.LocalTrace(child['target'], lazy._chooser(plan, child), children.operations,
                                           child['source_oid'], child_path),) if child is not None else ())
                for rest in walk(current, path):
                    yield Part((operation, *rest.operations), (*trace, *children.traces, *rest.traces),
                               _merge_pools((*( (pool,) if pool is not None else ()), *children.pools, *rest.pools)),
                               (stamp, *children.orders, *rest.orders), (*children.zero_terminals, *rest.zero_terminals))
        if unsupported or (wanted is not None and wanted.selected not in {c.id for c in available}):
            # A symbolic child can be identically zero under the joint vector.
            # In that case no actual unsupported replacement or choice occurs.
            yield Part(zero_terminals=(path,))

    def combine(index: int, packets: tuple[model.Packet, ...], prior: Part) -> Iterator[Layout]:
        if index == len(originals):
            frontier = model.Frontier(batch, packets, _merge_pools(prior.pools), destination_traces=prior.traces)
            yield Layout(frontier, prior.orders, prior.zero_terminals)
            return
        event = originals[index]
        path = str(event['_damage_lineage'])
        for part in walk(event, path):
            packet = model.Packet(path, event['source_oid'], event['target'], event.get('target_oid') or '',
                                  lazy._chooser(plan, event), int(event['amount']), part.operations, bool(event.get('unpreventable')))
            merged = Part(traces=(*prior.traces, *part.traces), pools=_merge_pools((*prior.pools, *part.pools)),
                          orders=(*prior.orders, *part.orders), zero_terminals=(*prior.zero_terminals, *part.zero_terminals))
            yield from combine(index + 1, (*packets, packet), merged)

    yield from combine(0, (), Part())


def witness(plan: Plan, events: list[dict[str, Any]], *, batch: str, orders: tuple[Order, ...] = (),
            numeric: tuple[tuple[str, str, int], ...] = ()) -> Completion | None:
    untouched = plan.state.model_dump_json()
    for layout in layouts(plan, events, batch=batch, orders=orders):
        solution = affine.witness(layout.frontier, numeric, zero_terminals=layout.zero_terminals)
        if solution is None:
            continue
        try:
            grounded = native.ground(plan, native.capture(plan, layout.frontier, json.loads(lazy.start(plan, events).originals)), solution)
        except ValueError:
            # A conservative symbolic layout is never sufficient proof by itself.
            # Actual native applicability must agree before a witness is returned.
            continue
        if plan.state.model_dump_json() != untouched:
            raise AssertionError('Symbolic completion mutated game state')
        return Completion(layout, solution, grounded)
    return None
