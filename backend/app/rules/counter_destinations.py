"""A resolving counterspell's controller chooses its counter destination."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan


def offer(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], targets: list[str]) -> bool:
    """True means the native counter instruction may proceed without pausing."""
    from app.rules import effects

    if not targets or not effects.counterable(plan, targets[0]):
        return True
    card = plan.state.cards[targets[0]]
    decide(plan, player=ctx['controller'], kind='choose_one', prompt=f'Put {card.name} on top or on the bottom of its owner\'s library if it is countered?',
           options=[DecisionOption(id='top', label='On top'), DecisionOption(id='bottom', label='On the bottom')],
           resume={'step': 'counter_destination', 'ctx': ctx, 'e': e, 'card': card.id, 'object': plan.oid(card)}, source=card)
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    r = d.resume
    ctx = r['ctx']
    fixed = {**r['e'], 'to': chosen[0], 'object': r['card'], 'object_oid': r['object']}
    # Run the selected native instruction through the normal preflight and continuation.
    # Neither the counter nor any of its events has happened while the choice is pending.
    index = ctx['next'] - 1
    ctx['effects'][index] = fixed
    ctx['next'] = index
    continue_effects(plan, ctx)
