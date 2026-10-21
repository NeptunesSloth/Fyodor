"""Native recipient reachability for exact joint-prevention markers.

This decides only which planner owns a batch. It never chooses a replacement,
allocates damage, spends a budget, or skips actual native grounding validation.
"""
from __future__ import annotations

import json
from dataclasses import replace as changed
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan
    from app.rules.replace import Candidate

MARKER = 'joint_prevention'


def eligible(plan: Plan, events: list[dict[str, Any]], candidates: list[Candidate]) -> bool:
    from app.rules import prevention_frontier_discovery as lazy
    from app.rules import replace, source_shields

    marked = [c for c in candidates if c.op.get(MARKER) is True]
    if not marked:
        return False
    for candidate in marked:
        if candidate.op.get('do') not in ('finite_prevention', 'redirect') or not candidate.op.get('allocate'):
            raise ValueError('A joint prevention marker requires a native allocated finite operation')
    positive = [event for event in events if int(event['amount']) > 0]
    if not positive:
        return False
    before = plan.state.model_dump_json()
    # A source and its traits stay fixed under native damage operations. Only
    # redirect can change a recipient. All numeric amounts stay with the actual
    # planner: this graph merely conservatively identifies reachable recipients.
    draft = lazy.start(plan, positive)
    planner = replace.Planner(plan, candidates, ask=False)
    for original in json.loads(draft.originals):
        if int(original['amount']) <= 0:
            continue
        pending = [original]
        seen: set[tuple[str, str]] = set()
        while pending:
            event = pending.pop()
            key = (event['target'], event.get('target_oid') or '')
            if key in seen:
                continue
            seen.add(key)
            sim = lazy._sim(plan)
            if any(planner.applies(c, event, sim) for c in marked):
                if plan.state.model_dump_json() != before:
                    raise AssertionError('Joint routing eligibility mutated game state')
                return True
            for candidate in candidates:
                if candidate.op.get('do') != 'redirect':
                    continue
                # Amount-changing predecessors can make a redirect's threshold
                # true. Relax only that routing predicate; actual discovery and
                # grounding retain the full native predicate and reject any
                # unsupported reachable operation rather than omitting it.
                match = {k: v for k, v in candidate.match.items() if k not in ('at_least', 'below_value')}
                edge = changed(candidate, match=match)
                if not planner.applies(edge, event, sim):
                    continue
                target = source_shields.redirect_target(plan, edge, event)
                if target is not None:
                    pending.append({**event, 'target': target,
                                    'target_oid': plan.oid(target) if target in plan.state.cards else None})
    if plan.state.model_dump_json() != before:
        raise AssertionError('Joint routing eligibility mutated game state')
    return False
