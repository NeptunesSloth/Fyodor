"""Combat damage benefits use the attacking player captured with the damage."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name) != ('Whenever ~ is dealt combat damage, you gain that much life '
                                                  'and attacking player loses that much life.'):
        return None
    return {'kind': 'triggered', 'trigger': 'event',
            'cond': {'event': 'dealt_damage', 'subject': 'self', 'combat': True},
            'effects': [{'do': 'combat_damage_life_receipt'}]}


def resolve(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    event = ctx.get('event') or {}
    amount = max(0, int(event.get('amount') or 0))
    attacker = event.get('attacking_player')
    if amount == 0:
        return True
    if attacker is None or attacker not in plan.state.players:
        decide(plan, player=ctx['controller'], kind='manual_resolution',
               prompt=(f'This older save did not record the attacking player. Gain {amount} life and have the '
                       f'original attacking player lose {amount} life by hand, then press Done.'),
               options=[DecisionOption(id='done', label='Done')],
               resume={'step': 'combat_damage_life_legacy', 'ctx': ctx})
        return False
    # Both instructions use the original damage amount; a gain replacement
    # changes the gain, never the nominal loss or its frozen beneficiary.
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do': 'gain_life', 'who': 'you', 'n': amount},
        {'do': 'lose_life', 'who': 'player:' + attacker, 'n': amount},
    ]
    return True


def legacy_done(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, decision.resume['ctx'])


PRIMITIVES = {'combat_damage_life_receipt': resolve}
RESUME = {'combat_damage_life_legacy': legacy_done}
