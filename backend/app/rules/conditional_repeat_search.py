"""CR 608.2c/d/h, 701.23/24: bounded optional searches and a deferred shuffle."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

_WORDING = re.compile(r'^(?:if (?P<lead>[^,]+), )?you may (?P<search>search your library [^.]+)\. '
                      r'then if (?P<cond>[^,]+), repeat this process once\. '
                      r'if you search your library this way, shuffle\.$', re.IGNORECASE)
_FLAG = '_conditional_repeat_searched'


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import conditions, scripts

    m = _WORDING.fullmatch(' '.join(body.split()))
    if m is None:
        return None
    cond = conditions.parse(m['cond'])
    first = conditions.parse(m['lead']) if m['lead'] else None
    search = scripts.parse_effects(m['search'][:1].upper() + m['search'][1:] + '.')
    if (cond is None or (m['lead'] and first is None) or search is None or search[1] is not None
            or search[2] or len(search[0]) != 1 or search[0][0].get('do') != 'search'
            or search[0][0].get('who', 'you') != 'you' or search[0][0].get('graveyard') or search[0][0].get('zones')):
        return None
    out: list[dict[str, Any]] = [{'do': 'conditional_repeat_search', 'cond': cond, 'remaining': 2,
            'search': {**search[0][0], 'shuffle': False}}, {'do': 'shuffle_if_repeat_searched'}]
    if first is not None:
        out.insert(0, {'do': 'only_if', 'cond': first, 'skip': len(out)})
    return out, None, False


def search_round(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import conditions, effects
    from app.rules.plan import decide

    if e['remaining'] == 2:
        ctx[_FLAG] = False
    if (e['remaining'] < 2 and not conditions.holds(plan, ctx, e['cond'])) or effects.barred_search(plan, ctx, e['search']):
        return True
    decide(plan, player=ctx['controller'], kind='confirm',
           prompt=f"{ctx.get('name') or 'It'}: search your library for a {e['search'].get('label') or 'card'}?",
           options=[DecisionOption(id='yes', label='Search'), DecisionOption(id='no', label="Don't search")],
           resume={'step': 'conditional_repeat_search', 'ctx': ctx, 'e': e})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume['ctx'], d.resume['e']
    more = [{**e, 'remaining': e['remaining'] - 1}] if e['remaining'] > 1 else []
    if chosen == ['yes']:
        ctx[_FLAG] = True
        more.insert(0, {**e['search'], 'may': False})
    at = ctx['next']
    ctx['effects'] = [*ctx['effects'][:at], *more, *ctx['effects'][at:]]
    effects.continue_effects(plan, ctx)


def shuffle(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    return not ctx.pop(_FLAG, False) or effects.shuffle_library(plan, ctx, {'do': 'shuffle_library', 'who': 'you'})


PRIMITIVES = {'conditional_repeat_search': search_round, 'shuffle_if_repeat_searched': shuffle}
RESUME = {'conditional_repeat_search': resume}
