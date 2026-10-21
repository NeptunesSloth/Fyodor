"""Unimported exact Research // Development continuations; no outside-game exception."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

RESEARCH = 'shuffle up to four cards you own from outside the game into your library'
DEVELOPMENT = 'create a 3/1 red elemental creature token unless any opponent has you draw a card. repeat this process two more times'


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    text = ' '.join(body.lower().split()).rstrip('.')
    if text == RESEARCH:
        # 903.11 disallows the import; 701.24d still instructs an empty-set shuffle.
        return [{'do': 'outside_permission'}, {'do': 'shuffle_library', 'who': 'you'}], None, False
    if text == DEVELOPMENT:
        return [{'do': 'development50', 'round': i} for i in range(3)], None, False
    return None


def _offer(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import scripts
    from app.rules.exile_packet_continuations import insert
    from app.rules.plan import decide

    order = e['order']
    i = e['i']
    while i < len(order) and order[i] not in plan.live():
        i += 1
    if i == len(order):
        got = scripts.parse_effects('Create a 3/1 red Elemental creature token.')
        assert got is not None
        return insert(ctx, got[0])
    decide(plan, player=order[i], kind='confirm', prompt='Have the caster draw a card instead of creating an Elemental?',
           options=[DecisionOption(id='yes', label='Draw a card'), DecisionOption(id='no', label='Create an Elemental')],
           # Native multiplayer departure recovery resumes grouped choices only
           # with these receipts: nobody has accepted, and these players remain.
           resume={'step': 'development50', 'ctx': ctx, 'e': {**e, 'i': i},
                   'rest': order[i + 1:], 'picked': []})
    return False


def development(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    return _offer(plan, ctx, {**e, 'order': [p for p in plan.apnap() if p != ctx['controller']], 'i': 0})


def resume_development(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects
    from app.rules.exile_packet_continuations import insert

    ctx, e = d.resume['ctx'], d.resume['e']
    if chosen == ['yes']:
        done = insert(ctx, [{'do': 'draw', 'who': 'you', 'n': 1}])
    else:
        done = _offer(plan, ctx, {**e, 'i': e['i'] + 1})
    if done:
        effects.continue_effects(plan, ctx)


PRIMITIVES = {'development50': development}
RESUME = {'development50': resume_development}
