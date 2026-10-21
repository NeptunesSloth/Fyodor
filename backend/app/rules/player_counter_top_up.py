"""CR 608.2h, 122.6: add the difference to a player's live counter total."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_WORDING = re.compile(r'^if (?P<who>target (?:player|opponent)) has fewer than (?P<n>[a-z]+|\d+) '
                      r'(?P<kind>poison|experience|energy|rad) counters, they get a number of (?P=kind) counters equal to the difference$')


def definition(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language, values
    from app.rules.scripts import _NoMatch

    total = int(m['n']) if m['n'].isdigit() else values.NUMBERS.get(m['n'])
    if total is None:
        raise _NoMatch
    kind, key, target = language.ref(m['who'])
    return [{'do': 'player_counter_top_up', 'who': language._who(kind, key),
             'counter': m['kind'], 'total': total}], target


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().rstrip('.')
    m = _WORDING.fullmatch(text[:1].lower() + text[1:])
    if m is None:
        return None
    from app.rules import language
    from app.rules.scripts import _NoMatch

    try:
        effects, target = definition(m)
    except _NoMatch:
        return None

    return effects, language._one(target), False


def top_up(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, replace

    puts = [(pid, e['counter'], max(0, e['total'] - plan.state.players[pid].resources.get(e['counter'], 0)))
            for pid in effects._players(plan, ctx, e['who'])]
    puts = [(pid, kind, n) for pid, kind, n in puts if n]
    return not puts or replace.put_counters(plan, puts, by=ctx['controller'], then=effects._then(ctx, e), ctx=ctx)


TEMPLATES = [(_WORDING, definition)]
PRIMITIVES = {'player_counter_top_up': top_up}
