"""Unregistered pure proof model for cyclic cross-recipient prevention budgets.

This is deliberately not a damage planner or card admission path. Local 616
traces are inputs; all pool vectors are solved jointly. Exhaustive enumeration
is suitable for the small proof cases, not the live engine. Redirect-created
branches retain applied candidate IDs and use the destination's local trace.
Discovery of native local choices remains outside this prototype.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import asdict, dataclass, replace
from typing import Literal


@dataclass(frozen=True)
class Operation:
    id: str
    kind: Literal['pool', 'multiply', 'protection']
    pool: str = ''
    factor: int = 1


@dataclass(frozen=True)
class Packet:
    lineage: str
    source_oid: str
    recipient: str
    recipient_oid: str
    affected_player: str
    amount: int
    operations: tuple[Operation, ...]
    unpreventable: bool = False


@dataclass(frozen=True)
class Pool:
    id: str
    controller: str
    remaining: int
    scope: Literal['turn', 'source_batch'] = 'turn'
    source_oids: tuple[str, ...] = ()
    mode: Literal['prevent', 'redirect'] = 'prevent'
    recipients: tuple[str, ...] = ()
    destination: str = ''
    destination_oid: str = ''
    destination_controller: str = ''


@dataclass(frozen=True)
class LocalTrace:
    recipient: str
    affected_player: str
    operations: tuple[Operation, ...]
    source_oid: str = ''  # Explicit legacy wildcard when both selectors are empty.
    lineage: str = ''


@dataclass(frozen=True)
class Selection:
    pool_group: str
    # Stable original lineage rows, never current packet iteration order.
    vector: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Frontier:
    batch: str
    packets: tuple[Packet, ...]
    pools: tuple[Pool, ...]
    selections: tuple[Selection, ...] = ()
    destination_traces: tuple[LocalTrace, ...] = ()

    def dumps(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(',', ':'))

    @classmethod
    def loads(cls, text: str) -> Frontier:
        data = json.loads(text)
        return cls(batch=data['batch'], packets=tuple(Packet(**{**p, 'operations': tuple(Operation(**o) for o in p['operations'])})
                    for p in data['packets']),
                   pools=tuple(Pool(**{**p, 'source_oids': tuple(p['source_oids']), 'recipients': tuple(p['recipients'])}) for p in data['pools']),
                   selections=tuple(Selection(s['pool_group'], tuple((row, n) for row, n in s['vector'])) for s in data['selections']),
                   destination_traces=tuple(LocalTrace(t['recipient'], t['affected_player'], tuple(Operation(**o) for o in t['operations']),
                                                             t.get('source_oid', ''), t.get('lineage', ''))
                                            for t in data['destination_traces']))


@dataclass(frozen=True)
class Solution:
    allocations: tuple[Selection, ...]
    residuals: tuple[tuple[str, int], ...]
    capacities: tuple[tuple[str, str, int], ...]
    # lineage, original source OID, current recipient, exact recipient OID,
    # current affected player, inherited applied candidate IDs.
    terminals: tuple[tuple[str, str, str, str, str, tuple[str, ...]], ...] = ()


def _pool(frontier: Frontier, ident: str) -> Pool:
    return next(p for p in frontier.pools if p.id == ident)


def group(frontier: Frontier, pool: Pool, packet: Packet) -> str:
    return json.dumps([pool.id, frontier.batch, packet.source_oid if pool.scope == 'source_batch' else None], separators=(',', ':'))


def _validate(frontier: Frontier) -> None:
    lineages = [p.lineage for p in frontier.packets]
    if len(lineages) != len(set(lineages)):
        raise ValueError('Original packet lineages must be distinct')
    if len({p.id for p in frontier.pools}) != len(frontier.pools):
        raise ValueError('Pool IDs must be distinct')
    if any(packet.amount < 0 for packet in frontier.packets):
        raise ValueError('Damage must be nonnegative')
    for operations in [*(p.operations for p in frontier.packets), *(t.operations for t in frontier.destination_traces)]:
        applied = set()
        for op in operations:
            if op.id in applied:
                raise ValueError('A candidate cannot apply twice to one packet')
            applied.add(op.id)
            if op.kind == 'multiply':
                if op.factor < 1:
                    raise ValueError('Only positive integer multipliers are modeled')
            elif op.kind == 'pool':
                pool = _pool(frontier, op.pool)
                if op.id != pool.id:
                    raise ValueError('Pool candidate IDs must remain stable across recipient traces')
                if pool.remaining < 0:
                    raise ValueError('Remaining budget must be nonnegative')
                if pool.mode == 'redirect' and not pool.destination:
                    raise ValueError('A redirection pool requires an exact destination')
    _validate_trace_selectors(frontier)


def _trace_choice(frontier: Frontier, recipient: str, controller: str, source_oid: str, lineage: str) -> tuple[int, LocalTrace]:
    matches = [(i, t) for i, t in enumerate(frontier.destination_traces)
               if t.recipient == recipient and (not t.source_oid or t.source_oid == source_oid)
               and (not t.lineage or t.lineage == lineage)]
    if not matches:
        raise ValueError('A redirect destination requires its own local 616 trace')
    specificity = max(bool(t.source_oid) + bool(t.lineage) for _, t in matches)
    chosen = [(i, t) for i, t in matches if bool(t.source_oid) + bool(t.lineage) == specificity]
    if len(chosen) != 1:
        raise ValueError('Ambiguous local trace selectors of the same specificity')
    index, found = chosen[0]
    if found.affected_player != controller:
        raise ValueError('The destination trace belongs to its affected player')
    return index, found


def _trace(frontier: Frontier, recipient: str, controller: str, source_oid: str = '', lineage: str = '') -> tuple[Operation, ...]:
    return _trace_choice(frontier, recipient, controller, source_oid, lineage)[1].operations


def _validate_trace_selectors(frontier: Frontier) -> None:
    known_sources = {p.source_oid for p in frontier.packets}
    identities = [(t.recipient, t.source_oid, t.lineage) for t in frontier.destination_traces]
    if len(identities) != len(set(identities)):
        raise ValueError('Duplicate local trace selectors')
    if any(t.source_oid and t.source_oid not in known_sources for t in frontier.destination_traces):
        raise ValueError('Unknown source selector in a local trace')
    used: set[int] = set()

    def visit(packet: Packet, path: str, recipient: str, operations: tuple[Operation, ...], applied: frozenset[str]) -> None:
        for op in operations:
            if op.id in applied:
                continue
            if op.kind == 'pool':
                pool = _pool(frontier, op.pool)
                eligible = ((pool.mode == 'redirect' or not packet.unpreventable)
                            and (not pool.source_oids or packet.source_oid in pool.source_oids)
                            and (not pool.recipients or recipient in pool.recipients))
                if not eligible:
                    continue
            applied |= {op.id}
            if op.kind == 'pool' and pool.mode == 'redirect':
                branch = json.dumps([path, op.id, pool.destination, pool.destination_oid], separators=(',', ':'))
                index, trace = _trace_choice(frontier, pool.destination, pool.destination_controller, packet.source_oid, branch)
                used.add(index)
                visit(packet, branch, pool.destination, trace.operations, applied)

    for packet in frontier.packets:
        visit(packet, packet.lineage, packet.recipient, packet.operations, frozenset())
    if any((t.source_oid or t.lineage) and i not in used for i, t in enumerate(frontier.destination_traces)):
        raise ValueError('Unknown or stale local trace selector')


def _walk(frontier: Frontier, values: dict[tuple[str, str], int] | None) -> tuple[
    list[tuple[str, str, int]], list[tuple[str, int]], list[tuple[str, str, str, str, str, tuple[str, ...]]],
    list[tuple[str, str]],
] | None:
    """Bounds retain both potential branches; evaluation uses the proposed vector."""
    capacities: list[tuple[str, str, int]] = []
    residuals = []
    terminals = []
    dependencies: list[tuple[str, str]] = []

    def visit(packet: Packet, path: str, recipient: str, oid: str, affected: str, n: int,
              operations: tuple[Operation, ...], applied: frozenset[str]) -> bool:
        for op in operations:
            if op.id in applied:
                continue
            if op.kind == 'multiply':
                applied = applied | {op.id}
                n *= op.factor
            elif op.kind == 'protection':
                applied = applied | {op.id}
                if values is not None and not packet.unpreventable:
                    n = 0
            elif op.kind == 'pool':
                pool = _pool(frontier, op.pool)
                eligible = ((pool.mode == 'redirect' or not packet.unpreventable)
                            and (not pool.source_oids or packet.source_oid in pool.source_oids)
                            and (not pool.recipients or recipient in pool.recipients))
                key = group(frontier, pool, packet)
                capacity = n if eligible else 0
                capacities.append((key, path, capacity))
                amount = min(capacity, pool.remaining) if values is None else values[key, path]
                if amount > capacity or amount < 0:
                    return False
                if values is not None:
                    n -= amount
                if not eligible:
                    continue
                dependencies.extend((group(frontier, earlier, packet), key) for earlier in frontier.pools
                                    if earlier.id in applied and earlier.id != pool.id)
                applied = applied | {op.id}
                if pool.mode == 'redirect':
                    branch = json.dumps([path, op.id, pool.destination, pool.destination_oid], separators=(',', ':'))
                    dest_ops = _trace(frontier, pool.destination, pool.destination_controller, packet.source_oid, branch)
                    if not visit(packet, branch, pool.destination, pool.destination_oid,
                                 pool.destination_controller, amount, dest_ops, applied):
                        return False
        residuals.append((path, n))
        terminals.append((path, packet.source_oid, recipient, oid, affected, tuple(sorted(applied))))
        return True

    for packet in frontier.packets:
        if not visit(packet, packet.lineage, packet.recipient, packet.recipient_oid,
                     packet.affected_player, packet.amount, packet.operations, frozenset()):
            return None
    return capacities, residuals, terminals, dependencies


def rows(frontier: Frontier) -> tuple[tuple[str, str, int], ...]:
    """Conservative independent bounds; no provisional prevention is applied."""
    _validate(frontier)
    walked = _walk(frontier, None)
    assert walked is not None
    out = [(key, path, min(capacity, _pool(frontier, json.loads(key)[0]).remaining)) for key, path, capacity in walked[0]]
    identities = [(g, row) for g, row, _ in out]
    if len(identities) != len(set(identities)):
        raise ValueError('A shared pool cannot apply twice to one original lineage')
    return tuple(sorted(out))


def _evaluate(frontier: Frontier, values: dict[tuple[str, str], int]) -> Solution | None:
    walked = _walk(frontier, values)
    if walked is None:
        return None
    rows_, residuals, terminals, _ = walked
    capacities = {(key, path): n for key, path, n in rows_}
    budgets = {key: _pool(frontier, json.loads(key)[0]).remaining for key, _, _ in rows_}
    allocations = []
    for key, budget in sorted(budgets.items()):
        vector = tuple(sorted((lineage, n) for (g, lineage), n in values.items() if g == key))
        capacity = sum(n for (g, _), n in capacities.items() if g == key)
        if sum(n for _, n in vector) != min(budget, capacity):
            return None
        allocations.append(Selection(key, vector))
    return Solution(tuple(allocations), tuple(sorted(residuals)), tuple(sorted(rows_)), tuple(sorted(terminals)))


def solutions(frontier: Frontier) -> tuple[Solution, ...]:
    """Solve the cyclic constraints together; no pool or recipient goes first."""
    variables = rows(frontier)
    selected = {(s.pool_group, row): n for s in frontier.selections for row, n in s.vector}
    if not set(selected) <= {(g, row) for g, row, _ in variables}:
        return ()
    domains = [(selected[g, row],) if (g, row) in selected else range(upper + 1) for g, row, upper in variables]
    out = []
    for proposed in itertools.product(*domains):
        if any(n < 0 or n > upper for n, (_, _, upper) in zip(proposed, variables, strict=True)):
            continue
        values = {(g, row): n for (g, row, _), n in zip(variables, proposed, strict=True)}
        solved = _evaluate(frontier, values)
        if solved is not None:
            out.append(solved)
    return tuple(out)


def options(frontier: Frontier, pool_group: str, actor: str) -> tuple[Selection, ...]:
    pool_id = json.loads(pool_group)[0]
    if _pool(frontier, pool_id).controller != actor:
        raise ValueError('Only the printed allocation controller may choose this vector')
    return tuple(sorted({s for sol in solutions(frontier) for s in sol.allocations if s.pool_group == pool_group}, key=lambda s: s.vector))


def choose(frontier: Frontier, selection: Selection, actor: str) -> Frontier:
    if selection not in options(frontier, selection.pool_group, actor):
        raise ValueError('This vector has no joint completion at the current local frontiers')
    return replace(frontier, selections=tuple(s for s in frontier.selections if s.pool_group != selection.pool_group) + (selection,))


def invalidate(frontier: Frontier, dirty_groups: frozenset[str]) -> Frontier:
    """Discard changed vectors and their capacity dependents, preserving others.

    The native caller must identify changed local frontiers/applicability. Cyclic
    pool groups invalidate their whole dependent component, not a guessed order.
    """
    _validate(frontier)
    walked = _walk(frontier, None)
    assert walked is not None
    dirty = set(dirty_groups)
    while True:
        descendants = {after for before, after in walked[3] if before in dirty}
        if descendants <= dirty:
            break
        dirty |= descendants
    return replace(frontier, selections=tuple(s for s in frontier.selections if s.pool_group not in dirty))
