"""Bounded counter riders keep target groups, casting receipts and token identities."""
from __future__ import annotations

from typing import Any

from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = body.strip().rstrip('.')
    if text == 'Put a +1/+1 counter on target creature you control. If this spell was cast from a graveyard, also put a +1/+1 counter on each other creature you control':
        native = scripts.parse_effects('Put a +1/+1 counter on target creature you control. If this spell was cast from a graveyard, put a +1/+1 counter on each creature you control.')
        assert native is not None
        return ([{**native[0][0], 'as': 'moment_target77'}, *native[0][1:-1], {**native[0][-1], 'exclude': 'moment_target77'}], native[1], native[2])
    if text == 'Target creature gets +2/+2 and gains trample until end of turn. Also put a +1/+1 counter on that creature if this spell was cast using teamwork':
        return scripts.parse_effects('Target creature gets +2/+2 and gains trample until end of turn. If this spell was cast using teamwork, put a +1/+1 counter on that creature.')
    if text == 'Create two 2/2 colorless Wizard Soldier creature tokens named Cadet. If this spell was cast from a graveyard, put a +1/+1 counter on each of them for every three cards in your graveyard':
        native = scripts.parse_effects('Create two 2/2 colorless Wizard Soldier creature tokens named Cadet. If this spell was cast from a graveyard, put a +1/+1 counter on each of them.')
        assert native is not None
        return ([*native[0][:-1], {**native[0][-1], 'do': 'recruited_counters77'}], native[1], native[2])
    if text == "Put a +1/+1 counter on target creature you control if its power is 4 or greater. Then that creature gets +1/+1 until end of turn and fights target creature you don't control":
        native = scripts.parse_effects("Target creature you control fights target creature you don't control.")
        assert native is not None
        return ([{'do': 'only_if', 'cond': {'object': 'target:0', 'stat': 'power', 'op': '>=', 'n': 4}, 'skip': 1},
                 {'do': 'add_counters', 'who': 'target:0', 'kind': '+1/+1', 'n': 1},
                 {'do': 'pump', 'who': 'target:0', 'p': 1, 't': 1}, *native[0]], native[1], False)
    return None


def recruited(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    n = len(plan.state.zones.get(ctx['controller'] + ':graveyard', [])) // 3
    return effects.add_counters(plan, ctx, {**e, 'do': 'add_counters', 'n': n})


PRIMITIVES = {'recruited_counters77': recruited}
