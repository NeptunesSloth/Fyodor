"""Unregistered completed lazy prefixes to joint constraints and native replay."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.rules import prevention_frontier_discovery as lazy
from app.rules import prevention_frontier_grounding as native
from app.rules import prevention_frontier_prototype as model

if TYPE_CHECKING:
    from app.rules.plan import Plan


@dataclass(frozen=True)
class Completed:
    frontier: model.Frontier
    solution: model.Solution
    grounded: native.Grounded
    snapshot: native.Snapshot


def complete(plan: Plan, draft: lazy.Draft, *, batch: str) -> Completed:
    """A complete provisional vector is validated, never committed or greedily repaired."""
    from app.rules import prevention_frontier_constraints as affine
    from app.rules import source_shields

    if draft.pending is not None:
        raise ValueError('The native pool owner has not answered')
    originals = json.loads(draft.originals)
    replay = lazy.start(plan, originals)
    if replay.candidates != draft.candidates:
        raise ValueError('Native frontier candidates changed')
    by_id = {c.id: c for c in lazy._candidates(plan, draft)}
    operations: dict[str, list[model.Operation]] = {}
    metadata: dict[str, tuple[str, str, str]] = {}
    destinations: dict[str, tuple[str, str, str]] = {}
    numeric: dict[tuple[str, str], int] = {}
    potential: dict[str, tuple[str, str, str]] = {}
    for pick in draft.picks:
        leaf = next(x for x in replay.leaves if x.id == pick.leaf)
        event = lazy._event(plan, leaf)
        candidate = by_id[pick.candidate]
        if pick.order_player != leaf.chooser or (pick.amount is not None and pick.allocation_player != candidate.controller):
            raise ValueError('The saved prefix has forged native chooser ownership')
        kind = candidate.op['do']
        if kind in ('finite_prevention', 'redirect'):
            operation = model.Operation(candidate.id, 'pool', pool=candidate.id)
            if pick.amount is None:
                raise ValueError('The saved finite pool has no numeric row')
            numeric[candidate.id, leaf.id] = pick.amount
            if kind == 'redirect':
                target = source_shields.redirect_target(plan, candidate, event)
                if target is None:
                    raise ValueError('The exact redirect destination is no longer representable')
                oid = plan.oid(target) if target in plan.state.cards else ''
                moved = {**event, 'target': target, 'target_oid': oid or None}
                destination = (target, oid, lazy._chooser(plan, moved))
                if candidate.id in destinations and destinations[candidate.id] != destination:
                    raise ValueError('A shared pool has source-dependent redirect destinations')
                destinations[candidate.id] = destination
                branch = json.dumps([leaf.id, candidate.id, target, oid], separators=(',', ':'))
                potential[branch] = (event['source_oid'], target, destination[2])
        elif kind == 'mul':
            operation = model.Operation(candidate.id, 'multiply', factor=int(candidate.op['n']))
        elif kind == 'prevent_all':
            operation = model.Operation(candidate.id, 'protection')
        else:
            raise ValueError('Unsupported completed native operation')
        operations.setdefault(leaf.id, []).append(operation)
        metadata[leaf.id] = (event['source_oid'], event['target'], leaf.chooser)
        replay = lazy.advance(plan, replay, leaf.id, candidate.id, amount=pick.amount)
    if replay != draft:
        raise ValueError('The saved native prefix does not replay exactly')
    if any(lazy.choices(plan, replay, leaf.id) for leaf in replay.leaves):
        raise ValueError('The native local replacement prefixes are incomplete')
    packets = tuple(model.Packet(str(e['_damage_lineage']), e['source_oid'], e['target'], e.get('target_oid') or '',
                                 lazy._chooser(plan, e), int(e['amount']), tuple(operations.get(str(e['_damage_lineage']), ())),
                                 bool(e.get('unpreventable'))) for e in originals)
    roots = {p.lineage for p in packets}
    traces = []
    for path, (source, target, chooser) in {**potential, **metadata}.items():
        if path not in roots:
            traces.append(model.LocalTrace(target, chooser, tuple(operations.get(path, ())), source, path))
    pools = []
    for candidate in by_id.values():
        if candidate.op['do'] not in ('finite_prevention', 'redirect'):
            continue
        if not any(op.pool == candidate.id for ops in operations.values() for op in ops):
            continue
        target, oid, chooser = destinations.get(candidate.id, ('', '', ''))
        pools.append(model.Pool(candidate.id, candidate.controller, int(candidate.op['limit']),
                                scope='source_batch' if candidate.op.get('budget_scope') == 'source_batch' else 'turn',
                                mode='redirect' if candidate.op['do'] == 'redirect' else 'prevent',
                                destination=target, destination_oid=oid, destination_controller=chooser))
    frontier = model.Frontier(batch, packets, tuple(pools), destination_traces=tuple(traces))
    rows = model.rows(frontier)
    values = {(group, row): numeric.get((json.loads(group)[0], row), 0) for group, row, _ in rows}
    # A complete concrete draft has one exact native amount per actual finite row.
    # Potential zero branches contribute explicit zero rows, never invented choices.
    selections = tuple(model.Selection(group, tuple(sorted((row, n) for (g, row), n in values.items() if g == group)))
                       for group in sorted({g for g, _ in values}))
    selected = model.Frontier(batch, packets, tuple(pools), selections, tuple(traces))
    solved = affine.witness(selected)
    exact = model._evaluate(frontier, values)
    if exact is None or solved is None or solved.allocations != exact.allocations:
        raise ValueError('The provisional native vector violates joint global budget entitlement')
    saved = native.capture(plan, selected, originals)
    grounded = native.ground(plan, saved, exact)
    return Completed(selected, exact, grounded, saved)
