"""CR 706.2b, 608.2c/d: an optional repeat of a resolved die-and-token block.

Each repeat rolls through the ordinary dice primitive, so advantage, ignored
dice, roll triggers, and deterministic history apply anew. Relative rewind
survives leading condition/target instructions and does not grow saved context.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import copying, language

    body = " ".join(body.split())
    body = body[:1].lower() + body[1:]
    if body != ('choose target creature you control, then roll a d20. '
                '1—14 | Create a tapped and attacking token that\'s a copy of that creature, except it\'s not legendary '
                'and it has "At end of combat, exile this token." '
                '15—20 | Create one of those tokens. You may roll again.'):
        return None
    ex = copying.parse_excepts('it\'s not legendary and it has "At end of combat, exile this token."')
    assert ex is not None
    return ([{'do': 'roll', 'sides': 20, 'count': 1},
             {'do': 'token_copy', 'who': 'target:0', 'n': 1, 'tapped': True, 'attacking': True,
              'excepts': [ex.model_dump(mode='json', exclude_defaults=True)]},
             {'do': 'optional_repeat_roll', 'min': 15, 'max': 20, 'rewind': 3}],
            [language.target_group('target creature you control')], False)


def repeat(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    result = int(ctx.get('die') or 0)
    if not e['min'] <= result <= e['max']:
        return True
    decide(plan, player=ctx['controller'], kind='confirm',
           prompt=f"{ctx.get('name') or 'Die roll'}: roll again?",
           options=[DecisionOption(id='yes', label='Roll again'), DecisionOption(id='no', label='Stop rolling')],
           resume={'step': 'optional_repeat_roll', 'ctx': ctx, 'rewind': int(e['rewind'])})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx = d.resume['ctx']
    if chosen == ['yes']:
        ctx['next'] -= d.resume['rewind']
    continue_effects(plan, ctx)


PRIMITIVES = {'optional_repeat_roll': repeat}
RESUME = {'optional_repeat_roll': resume}
