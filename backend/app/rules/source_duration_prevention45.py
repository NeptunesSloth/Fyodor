"""Exact Saga chapter shield bound to its original source's battlefield stay."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'source_duration_prevention45'
BODY = 'Prevent all damage that would be dealt by up to one target creature for as long as ~ remains on the battlefield.'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body != BODY:
        return None
    return ([{'do': STEP}], [{'what': 'creature', 'min': 0, 'max': 1}], False)


def run(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import delayed, effects, replace

    if not delayed._source_ok(plan, 'source_on_battlefield', ctx.get('source_card'), ctx.get('source_object'), ctx.get('controller')):
        return True
    targets = effects._cards(plan, ctx, 'target')
    if not targets:
        return True
    replace.add_record(plan, controller=ctx['controller'], label=ctx.get('name') or "Old Fat Spider Can't See Me",
                       event='damage', source=ctx.get('source_object'), source_card=ctx.get('source_card'),
                       match={'source': {'oids': [plan.oid(targets[0])]}},
                       op={'do': 'prevent_all', 'prevention': True}, until='source_on_battlefield')
    return True


PRIMITIVES = {STEP: run}
