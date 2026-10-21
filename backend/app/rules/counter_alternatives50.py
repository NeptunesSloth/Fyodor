"""Choose between fixed counter instructions during resolution, using native effects."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_FIXED = re.compile(
    r"Put a (?P<kind>[a-z][a-z -]*) counter on (?P<who>~|target Saga you control) "
    r"or remove (?P<removed>one|a [a-z][a-z -]* counter) from it\."
)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language

    m = _FIXED.fullmatch(body.strip())
    if m is None or m['removed'] not in ('one', f"a {m['kind']} counter"):
        return None
    kind, key, group = language.ref(m['who'])
    if kind not in ('target', 'self'):
        return None
    who = language._who(kind, key)
    return [{'do': 'counter_alternative50', 'who': who, 'kind': m['kind']}], language._one(group), False


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, prohibitions, resolution_choice

    recipients = effects._cards(plan, ctx, e['who'])
    if len(recipients) != 1:
        return True
    cid, counter = recipients[0], e['kind']
    options = []
    if not prohibitions.cant_counters(plan, cid, None, counter):
        options.append({'label': f'Put a {counter} counter on it', 'effects': [
            {'do': 'add_counters', 'who': e['who'], 'kind': counter, 'n': 1}]})
    if (plan.state.cards[cid].counters.get(counter, 0) > 0
            and not prohibitions.cant_remove_counters(plan, cid, counter)):
        options.append({'label': f'Remove a {counter} counter from it', 'effects': [
            {'do': 'remove_counters', 'who': e['who'], 'kind': counter, 'n': 1}]})
    if len(options) == 1:
        at = ctx['next']
        ctx['effects'] = [*ctx['effects'][:at], *options[0]['effects'], *ctx['effects'][at:]]
        return True
    if not options:
        return True
    return resolution_choice.pick_one(plan, ctx, {'options': options})


PRIMITIVES = {'counter_alternative50': run}
