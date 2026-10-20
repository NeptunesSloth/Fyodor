"""Unregistered proved frontier to native DamagePlan adapter; never commits."""
from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan
    from app.rules.prevention_frontier_joint_draft import Completed
    from app.rules.replace import DamagePlan


def damage_plan(plan: Plan, completed: Completed, events: list[dict[str, Any]]) -> DamagePlan:
    from app.rules import prevention_frontier_discovery as lazy
    from app.rules import prevention_frontier_grounding as native
    from app.rules import prevention_frontier_prototype as model
    from app.rules import replace, replacements

    untouched = plan.state.model_dump_json()
    normalized = lazy.start(plan, events)
    if normalized.originals != completed.snapshot.events or normalized.candidates != completed.snapshot.candidates:
        raise ValueError('The native damage caller differs from the proved original batch')
    grounded = native.ground(plan, completed.snapshot, completed.solution)
    if grounded != completed.grounded:
        raise ValueError('The native damage solution changed before conversion')
    by_path = {str(event['_redirect_lineage']): event for event in grounded.events}
    values = {(selection.pool_group, row): n for selection in completed.solution.allocations for row, n in selection.vector}
    ordered = []

    def visit(packet: model.Packet, path: str, operations: tuple[model.Operation, ...], inherited: frozenset[str]) -> None:
        applied = inherited
        for operation in operations:
            if operation.id in applied:
                continue
            applied |= {operation.id}
            if operation.kind == 'pool':
                pool = next(p for p in completed.frontier.pools if p.id == operation.pool)
                group = model.group(completed.frontier, pool, packet)
                if pool.mode == 'redirect' and values[group, path] > 0:
                    branch = json.dumps([path, operation.id, pool.destination, pool.destination_oid], separators=(',', ':'))
                    trace = model._trace(completed.frontier, pool.destination, pool.destination_controller, packet.source_oid, branch)
                    visit(packet, branch, trace, applied)
        if path in by_path:
            ordered.append(by_path[path])

    for packet in completed.frontier.packets:
        visit(packet, packet.lineage, packet.operations, frozenset())
    if len(ordered) != len(grounded.events) or {id(e) for e in ordered} != {id(e) for e in grounded.events}:
        raise ValueError('The native terminal order cannot be represented exactly')
    originals = json.loads(completed.snapshot.events)
    notes = []
    for before in originals:
        for after in ordered:
            if after.get('_damage_lineage') != before['_damage_lineage'] or not after.get('why'):
                continue
            who = replacements._label(plan, before['target'])
            why = ', '.join(dict.fromkeys(after['why']))
            if after['amount'] <= 0:
                notes.append(f"{before['amount']} damage to {who} prevented ({why})")
            elif after['target'] != before['target']:
                notes.append(f"{why}: {after['amount']} damage to {replacements._label(plan, after['target'])} instead of {who}")
            else:
                notes.append(f"{why}: {after['amount']} damage to {who} instead of {before['amount']}")
    planner = replace.Planner(plan, replace.damage_candidates(plan), ask=False)
    planner.used = list(dict.fromkeys(candidate for event in ordered for candidate in event.get('applied') or []))
    result = replace.DamagePlan(copy.deepcopy(ordered), notes, dict(grounded.shields), planner)
    if plan.state.model_dump_json() != untouched:
        raise AssertionError('Native DamagePlan conversion mutated game state')
    return result
