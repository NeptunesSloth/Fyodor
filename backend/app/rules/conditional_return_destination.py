"""CR 608.2c, 608.2h: optionally replace a graveyard return's destination."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

BODY = ('You may return target nonland permanent card from your graveyard to your hand. '
        'If that land is a Plains, you may return that nonland permanent card to the battlefield instead.')


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    text = body[:1].upper() + body[1:]
    if text != BODY:
        return None
    base = scripts._parse_effects_plain('Return target nonland permanent card from your graveyard to your hand.')
    plains = selectors.parse('Plains')
    assert base is not None and plains is not None
    return ([{'do': 'choose_return_destination', 'return': base[0][0],
              'condition': {'object': 'event', 'is': plains.key()}}], base[1], False)


def choose(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import conditions, effects
    from app.rules.plan import decide

    if not effects._cards(plan, ctx, e['return']['who']):
        return True
    options = [DecisionOption(id='hand', label='Return it to your hand')]
    if conditions.holds(plan, ctx, e['condition']):
        options.append(DecisionOption(id='battlefield', label='Return it to the battlefield instead'))
    options.append(DecisionOption(id='decline', label='Leave it in the graveyard'))
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Choose whether and where to return the card', options=options,
           resume={'step': 'conditional_return_destination', 'ctx': ctx, 'return': e['return']})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume['ctx']
    if chosen[0] == 'decline' or effects.return_card(plan, ctx, {**d.resume['return'], 'to': chosen[0], 'under': 'you'}):
        effects.continue_effects(plan, ctx)


PRIMITIVES = {'choose_return_destination': choose}
RESUME = {'conditional_return_destination': resume}
