"""Barrowgoyf's optional mill cost uses the prepared native mill producer."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_BODY = 'You may mill that many cards. If you do, you may put a creature card from among them into your hand.'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules.selectors import Selector

    if body.strip().casefold() != _BODY.casefold():
        return None
    sel = Selector(card=True, zones=('graveyard', 'exile', 'battlefield', 'command', 'stack'), types=('Creature',))
    return [{'do': 'optional_mill_cost64', 'n': {'event_amount': 1}},
            {'do': 'only_if', 'cond': {'flag': 'paid_mill64'}, 'skip': 2},
            {'do': 'mill', 'who': 'you', 'n': {'event_amount': 1}, 'as': 'barrow_mill64'},
            {'do': 'pick_looked', 'who': 'ref:barrow_mill64', 'public_mill59': True, 'sel': sel.key(),
             'n': 1, 'to': 'hand', 'optional': True}], None, False


def choose(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects
    from app.rules.plan import decide

    context.bind_flag(ctx, 'paid_mill64', False)
    n = effects._amount(plan, ctx, e['n'])
    if n <= 0:
        raise ActionError('The original positive combat damage amount is required')
    # 701.17b and118.3 prohibit choosing a mill cost without the full library resources.
    if len(effects._library(plan, ctx['controller'])) < n:
        return True
    decide(plan, player=ctx['controller'], kind='confirm', prompt=f'You may mill {n} cards',
           options=[DecisionOption(id='yes', label=f'Mill {n} cards'), DecisionOption(id='no', label='Decline')],
           resume={'step': 'optional_mill_cost64', 'ctx': ctx, 'n': n})
    return False


def answer(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    n = d.resume.get('n')
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        raise ActionError('The original positive combat damage amount is required')
    ctx = d.resume['ctx']
    context.bind_flag(ctx, 'paid_mill64', chosen[0] == 'yes')
    # The native producer freezes its own original draw order and replacement decisions.
    if chosen[0] == 'yes':
        ctx['effects'][ctx['next'] + 1] = {**ctx['effects'][ctx['next'] + 1], 'n': n}
    effects.continue_effects(plan, ctx)


PRIMITIVES = {'optional_mill_cost64': choose}
RESUME = {'optional_mill_cost64': answer}
