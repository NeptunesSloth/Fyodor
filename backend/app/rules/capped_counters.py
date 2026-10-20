"""Optional counter amounts with a ceiling on the resulting total (101.2, 609.3)."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

_FORM = re.compile(r"put up to X (?P<kind>[+-]\d+/[+-]\d+) counters on (?P<self>~|this creature)\. "
                   r"This ability can't cause the total number of (?P=kind) counters on (?P=self) to be greater than (?P<cap>\w+)\.?", re.I)
_KEY = '_capped_counter_choices'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import values

    m = _FORM.fullmatch(body.strip())
    if m is None or not isinstance(cap := values.parse_amount(m['cap']), int) or cap < 0:
        return None
    return [{'do': 'capped_counters', 'kind': m['kind'], 'n': {'x': 1}, 'cap': cap}], None, False


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, group_choice, replace
    from app.rules.plan import decide

    source = effects._cards(plan, ctx, 'self')
    if not source:
        return True
    cid = source[0]
    room = max(0, e['cap'] - plan.state.cards[cid].counters.get(e['kind'], 0))
    most = max(0, effects._amount(plan, ctx, e['n']))
    if room == 0 or most == 0:
        return True
    key = str(int(ctx.get('next') or 0) - 1)
    choices = ctx.setdefault(_KEY, {})
    if key not in choices:
        decide(plan, player=ctx['controller'], kind='choose_one', prompt=f"{ctx.get('name') or 'It'}: put up to {most} {e['kind']} counters",
               options=[DecisionOption(id=group_choice.NUMBER, label=f'Type a number from 0 to {most}', group='number'),
                        DecisionOption(id='pass', label='Put no counters')],
               source=plan.state.cards[cid], resume={'step': 'capped_counters', 'ctx': ctx, 'e': e, 'most': most})
        return False
    amount = min(int(choices[key]), most)
    answers = replace._ctx_answers(ctx)
    planned = replace.plan_counters(plan, [(cid, e['kind'], amount)], by=ctx['controller'], effect=True,
                                    entering=None, answers=answers, ask=True)
    if isinstance(planned, replace.Ask):
        then = replace.rerun_then(ctx, e)
        assert then is not None
        replace.ask(plan, planned, answers, then)
        return False
    # A replacement can increase the amount. The ability's prohibition still bounds
    # its final event, and doesn't limit another object's or another kind's counters.
    oid = context.ref_of(plan, cid)
    for _, out in planned.finals:
        for ev in out:
            if ev.get('card') == cid and oid is not None and ev.get('oid') == oid.object_id and ev.get('counter') == e['kind']:
                ev['n'] = min(max(0, int(ev['n'])), room)
                room -= ev['n']
    replace.do_counters(plan, planned, by=ctx['controller'])
    choices.pop(key, None)
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume['ctx'], d.resume['e']
    n = 0 if chosen[0] == 'pass' else int(chosen[0])
    if n > int(d.resume['most']):
        raise ActionError('That is more counters than this ability can put')
    ctx.setdefault(_KEY, {})[str(int(ctx.get('next') or 0) - 1)] = n
    if run(plan, ctx, e):
        effects.continue_effects(plan, ctx)
