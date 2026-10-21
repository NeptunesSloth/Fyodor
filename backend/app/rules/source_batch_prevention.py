"""Opt-in static source-batch budget key and isolated projection prototype.

The native finite-prevention route reads/writes ``budget_key`` directly. The
isolated projection remains available for pure adapter prototypes. Candidate/applied/receipt identities never change.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan
    from app.rules.replace import Candidate


def budget_key(candidate: Candidate, event: dict[str, Any]) -> str:
    import json

    if candidate.op.get('budget_scope') != 'source_batch':
        return 'limited:' + candidate.id
    if candidate.op.get('do') != 'finite_prevention' or not candidate.id.startswith('s:'):
        raise ValueError('Source-batch prevention requires an explicit static finite pool')
    if not event.get('source_oid'):
        raise ValueError('Source-batch prevention requires the original damage source OID')
    return 'source_limited:' + json.dumps([candidate.id, event['source_oid']], separators=(',', ':'))


@contextmanager
def _projection(candidate: Candidate, event: dict[str, Any], sim: dict[str, Any], *, consume: bool) -> Iterator[None]:
    shields = sim.setdefault('shields', {})
    ordinary = 'limited:' + candidate.id
    scoped = budget_key(candidate, event)
    existed = ordinary in shields
    previous = shields.get(ordinary)
    shields[ordinary] = int(shields.get(scoped, candidate.op['limit']))
    succeeded = False
    try:
        yield
        succeeded = True
    finally:
        if consume and succeeded:
            shields[scoped] = int(shields[ordinary])
        if existed:
            shields[ordinary] = previous
        else:
            shields.pop(ordinary, None)


def applies(plan: Plan, candidate: Candidate, event: dict[str, Any], sim: dict[str, Any], *,
            native: Callable[[Plan, Candidate, dict[str, Any], dict[str, Any]], bool]) -> bool:
    if candidate.op.get('budget_scope') != 'source_batch':
        return native(plan, candidate, event, sim)
    with _projection(candidate, event, sim, consume=False):
        return native(plan, candidate, event, sim)


def apply(plan: Plan, candidate: Candidate, event: dict[str, Any], sim: dict[str, Any], *,
          native: Callable[[Plan, Candidate, dict[str, Any], dict[str, Any]], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if candidate.op.get('budget_scope') != 'source_batch':
        return native(plan, candidate, event, sim)
    with _projection(candidate, event, sim, consume=True):
        return native(plan, candidate, event, sim)
