"""Unregistered replay proof for a complete joint allocation, never a live planner.

Local orders and global allocations must already be proved by the pure model.
Native operations ground the result without committing damage or consuming pools.
Unsupported operations and stale predicates fail closed; no fallback picks an order.
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from app.rules import prevention_frontier_prototype as model

if TYPE_CHECKING:
    from app.rules.plan import Plan
    from app.rules.replace import Candidate


@dataclass(frozen=True)
class Snapshot:
    frontier: str
    events: str
    candidates: str

    def dumps(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def loads(cls, text: str) -> Snapshot:
        return cls(**json.loads(text))


@dataclass(frozen=True)
class Grounded:
    events: tuple[dict[str, Any], ...]
    shields: dict[str, int]
    receipts: tuple[dict[str, Any], ...]


def _canonical(candidates: list[Candidate]) -> str:
    return json.dumps(sorted((asdict(c) for c in candidates), key=lambda c: c['id']), sort_keys=True)


def capture(plan: Plan, frontier: model.Frontier, events: list[dict[str, Any]]) -> Snapshot:
    from app.rules import replace

    return Snapshot(frontier.dumps(), json.dumps(events, sort_keys=True), _canonical(replace.damage_candidates(plan)))


def _supported(c: Candidate) -> None:
    if (c.event != 'damage' or c.legacy is not None or c.self_repl
            or c.op.get('once') or c.op.get('optional') or c.op.get('external_optional')
            or c.match.get('at_least') or c.match.get('below_value') is not None):
        raise ValueError('Unsupported candidate or amount-dependent predicate')
    kind = c.op.get('do')
    if kind == 'mul' and set(c.op) == {'do', 'n'} and int(c.op['n']) >= 1:
        return
    if kind == 'prevent_all' and c.prevention:
        allowed = {'do', 'prevention', 'protection_target', 'protection_object', 'rider'}
        if c.op.get('consume_unpreventable') is True and c.op.get('rider'):
            allowed.add('consume_unpreventable')
        if not (set(c.op) - allowed):
            return
    if kind in ('finite_prevention', 'redirect') and c.op.get('allocate') and int(c.op.get('limit', -1)) >= 0:
        allowed = {'do', 'allocate', 'limit', 'prevention', 'rider', 'to', 'oid', 'pid', 'budget_scope', 'joint_prevention'}
        if not (set(c.op) - allowed):
            return
    raise ValueError(f'Unsupported native damage operation: {c.op!r}')


def ground(plan: Plan, saved: Snapshot, solution: model.Solution, *, reverse: bool = False) -> Grounded:
    """Replay approved rows through native applies/apply, rejecting any semantic gap.

    This prototype does not discover 616 orders, ask choices, resume callers,
    or commit results. The opt-in source-batch key route does not admit a card.
    """
    from app.rules import (
        prevention_receipts,
        replace,
        single_recipient_redirection,
        source_batch_prevention,
        source_shields,
    )

    untouched = plan.state.model_dump_json()
    frame = model.Frontier.loads(saved.frontier)
    model._validate(frame)
    candidates = replace.damage_candidates(plan)
    if _canonical(candidates) != saved.candidates:
        raise ValueError('Native candidates changed since the frontier snapshot')
    by_id = {c.id: c for c in candidates}
    values = {(s.pool_group, row): n for s in solution.allocations for row, n in s.vector}
    expected_rows = {(group, row) for group, row, _ in model.rows(frame)}
    if (set(values) != expected_rows or len(values) != sum(len(s.vector) for s in solution.allocations)):
        raise ValueError('The complete joint allocation is not a proved solution')
    if any(values.get((s.pool_group, row)) != n for s in frame.selections for row, n in s.vector):
        raise ValueError('The complete joint allocation contradicts an approved selection')
    if model._evaluate(frame, values) != solution:
        raise ValueError('The complete joint allocation is not a proved solution')
    for pool in frame.pools:
        c = by_id.get(pool.id)
        if pool.scope == 'source_batch':
            if c is None or c.op.get('budget_scope') != 'source_batch' or pool.mode != 'prevent' or not c.id.startswith('s:'):
                raise ValueError('Source-batch native pool keys require an explicit static source-batch operation')
        elif c is not None and c.op.get('budget_scope'):
            raise ValueError('Native pool scope differs from the proved scope')
        if (c is None or c.controller != pool.controller or c.op.get('limit') != pool.remaining
                or c.op.get('do') != ('redirect' if pool.mode == 'redirect' else 'finite_prevention')
                or c.prevention != (pool.mode == 'prevent')):
            raise ValueError('Pool budget, ownership or native operation disagrees')
    events = json.loads(saved.events)
    if len(events) != len(frame.packets):
        raise ValueError('Original native packet count changed')
    planner = replace.Planner(plan, candidates, ask=False)
    sim: dict[str, Any] = {'shields': {k: int(v) for k, v in plan.rules.prevention.items()}, 'redirect_allocations': {}}
    final: list[tuple[str, dict[str, Any]]] = []

    def visit(packet: model.Packet, event: dict[str, Any], path: str, operations: tuple[model.Operation, ...]) -> None:
        ev = copy.deepcopy(event)
        ev['_redirect_lineage'] = path
        for op in operations:
            if op.kind not in ('pool', 'multiply', 'protection'):
                raise ValueError('Unsupported modeled local operation')
            if op.id in ev.get('applied', []):
                continue
            # Zero damage is not a damage event (614.7a). The model retains
            # zero-capacity rows solely to represent complete global vectors.
            if int(ev['amount']) <= 0:
                break
            c = by_id.get(op.id)
            if c is None:
                raise ValueError('Local trace names a missing native candidate')
            for candidate in candidates:
                if planner.applies(candidate, ev, sim):
                    _supported(candidate)
            # Other currently eligible candidates may cease to apply after this
            # choice (zero damage or a redirect). Only a positive final frontier
            # requires all remaining native candidates to have been handled.
            if op.kind == 'pool':
                pool = next(p for p in frame.pools if p.id == op.pool)
                eligible = (pool.remaining > 0 and (pool.mode == 'redirect' or not packet.unpreventable)
                            and (not pool.source_oids or packet.source_oid in pool.source_oids)
                            and (not pool.recipients or ev['target'] in pool.recipients))
                n = values[model.group(frame, pool, packet), path]
                if not eligible:
                    if n != 0 or planner.applies(c, ev, sim):
                        raise ValueError('Native pool predicate differs from the proved frontier')
                    continue
                identity = single_recipient_redirection.identity(c, ev)
                row = path + ':' + ','.join(ev.get('applied') or [])
                sim['redirect_allocations'].setdefault(identity, {})[row] = n
            elif op.kind == 'multiply':
                if c.op != {'do': 'mul', 'n': op.factor}:
                    raise ValueError('Native multiplier changed')
            elif op.kind == 'protection':
                if c.op.get('do') != 'prevent_all':
                    raise ValueError('Protection trace is not native full prevention')
                if packet.unpreventable and not planner.applies(c, ev, sim):
                    continue
            if not planner.applies(c, ev, sim):
                raise ValueError('Native candidate predicate differs from the local trace')
            before_amount = int(ev['amount'])
            budget_key = ('redir:' + c.id if op.kind == 'pool' and pool.mode == 'redirect'
                          else source_batch_prevention.budget_key(c, ev))
            before_budget = int(sim['shields'].get(budget_key, c.op.get('limit', 0)))
            children = planner.apply(c, ev, sim)
            if op.kind == 'pool':
                if sim['shields'].get(budget_key) != before_budget - n:
                    raise ValueError('Native pool consumption differs from the approved allocation')
                if pool.mode == 'prevent' and (len(children) != 1 or children[0]['amount'] != before_amount - n):
                    raise ValueError('Native prevention differs from the approved allocation')
            if op.kind == 'pool' and pool.mode == 'redirect':
                if n == 0:
                    if len(children) != 1 or children[0]['target'] != ev['target']:
                        raise ValueError('Zero redirect changed the event')
                    ev = children[0]
                    continue
                moved = children[0]
                if moved['amount'] != n or sum(child['amount'] for child in children) != before_amount:
                    raise ValueError('Native redirect split differs from the approved allocation')
                if (moved['target'] != pool.destination or (moved.get('target_oid') or '') != pool.destination_oid
                        or replace.affected(plan, moved) != pool.destination_controller):
                    raise ValueError('Native redirect destination differs from the joint frontier')
                branch = json.dumps([path, op.id, pool.destination, pool.destination_oid], separators=(',', ':'))
                operations_at_destination = model._trace(frame, pool.destination, pool.destination_controller, packet.source_oid, branch)
                visit(packet, moved, branch, operations_at_destination)
                if len(children) == 1:
                    return
                ev = children[1]
            else:
                if len(children) != 1:
                    raise ValueError('Native operation unexpectedly split damage')
                ev = children[0]
        if int(ev['amount']) > 0:
            for candidate in candidates:
                if planner.applies(candidate, ev, sim):
                    _supported(candidate)
            unapplied = planner.applicable(ev, sim)
            if unapplied:
                raise ValueError('An applicable native candidate is missing after the local trace')
        if any(ev.get(k) != event.get(k) for k in ('source_card', 'source_oid', 'src', 'kw', 'lkey', 'combat', 'unpreventable')):
            raise ValueError('Native replay changed original damage source or traits')
        final.append((path, ev))

    paired = list(zip(frame.packets, events, strict=True))
    if reverse:
        paired.reverse()
    for packet, event in paired:
        if (event.get('kind') != 'damage' or event['amount'] != packet.amount
                or event.get('source_oid') != packet.source_oid or event['target'] != packet.recipient
                or (event.get('target_oid') or '') != packet.recipient_oid
                or replace.affected(plan, event) != packet.affected_player
                or bool(source_shields.unpreventable(plan, event)) != packet.unpreventable
                or event.get('applied')):
            raise ValueError('Original native event identity, chooser or traits changed')
        if packet.recipient in plan.state.cards and plan.oid(packet.recipient) != packet.recipient_oid:
            raise ValueError('Original native recipient incarnation changed')
        event.setdefault('_damage_lineage', packet.lineage)
        visit(packet, event, packet.lineage, packet.operations)
    actual = sorted((path, e['target'], e.get('target_oid') or '', e['amount'], e.get('source_oid'), replace.affected(plan, e))
                    for path, e in final if int(e['amount']) > 0)
    residuals = dict(solution.residuals)
    expected = sorted((path, target, oid, residuals[path], source, chooser)
                      for path, source, target, oid, chooser, _ in solution.terminals if residuals[path] > 0)
    if actual != expected:
        raise ValueError('Native replay does not equal the complete joint solution')
    if plan.state.model_dump_json() != untouched:
        raise AssertionError('Pure grounding mutated the native game state')
    result_events = tuple(e for _, e in sorted(final, key=lambda row: row[0]))
    return Grounded(result_events, dict(sim['shields']), tuple(prevention_receipts.collect(list(result_events))))
