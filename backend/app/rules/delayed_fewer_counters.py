"""CR 608.2h, 603.7c: freeze a dead object's counters for its delayed return."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

BODY = re.compile(r'Return (?:it|~|this card) to the battlefield with one fewer (?P<kind>[a-z]+) counter on it '
                  r'at the beginning of the next end step\.')


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    text = body[:1].upper() + body[1:]
    gate = re.match(r"If it had a (?P<kind>[a-z]+) counter on it, ", text)
    if gate is not None:
        text = text[gate.end():]
        text = text[:1].upper() + text[1:]
    m = BODY.fullmatch(text)
    if m is None:
        return None
    if gate is not None and gate['kind'] != m['kind']:
        return None
    effects: list[dict[str, Any]] = [{'do': 'delay_return_fewer_counters', 'counter': m['kind']}]
    if gate is not None:
        effects.insert(0, {'do': 'only_if', 'cond': {'object': 'event', 'counters': m['kind']}, 'skip': 1})
    return effects, None, False


def schedule(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, delayed, values

    objects = [r.model_dump(mode='json') for r in context._object_refs(ctx, context.EVENT_NEW)
               if r.zone is not None and r.zone.endswith(':graveyard')]
    n = max(0, values.evaluate(plan, ctx, {'counters': e['counter'], 'on': 'event'}) - 1)
    refs = {'delayed_return': {'kind': 'objects', 'objects': objects}}
    # The integer is fixed now. Entry replacements remain native and apply later,
    # when this exact graveyard incarnation would return, including merged cards.
    delayed.create_plain(plan, ctx['controller'], ctx['source_card'], ctx['source_object'], ctx.get('name') or 'A creature',
                         {'kind': 'step', 'step': 'end', 'whose': 'next'},
                         [{'do': 'bind_refs', 'refs': refs},
                          {'do': 'return_card', 'who': 'ref:delayed_return', 'to': 'battlefield', 'under': 'owner',
                           **({'counter': e['counter'], 'counter_n': n} if n else {})}])
    return True


PRIMITIVES = {'delay_return_fewer_counters': schedule}
