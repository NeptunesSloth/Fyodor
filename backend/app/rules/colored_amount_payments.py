"""Optional typed amounts of one mana color, including paying zero (118.12)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan


def start(plan: Plan, ctx: dict[str, Any], payer: str, bind: str, color: str) -> bool:
    from app.rules import group_choice, optional_payment
    from app.rules.plan import decide

    decide(plan, player=payer, kind='choose_one', prompt=f"{ctx.get('name') or 'It'}: pay any amount of {{{color}}}",
           options=[DecisionOption(id=group_choice.NUMBER, label='Type a number ≥ 0', group='number'),
                    DecisionOption(id='pass', label="Don't pay")],
           source=plan.state.cards.get(ctx.get('source_card') or ''),
           resume={'step': optional_payment.STEP, 'ctx': ctx, 'cost': f'{{{color}}}',
                   'choose_x': {'bind': bind, 'payer': payer, 'color': color}})
    return False


def _available_upper_bound(plan: Plan, payer: str, color: str) -> int:
    """A cheap upper bound before constructing any amount-sized cost or string.

    Filter inputs and mutually exclusive source abilities can overestimate it;
    the real solver below still validates the complete payment atomically.
    """
    from app.rules import casting, mana_units

    player = plan.state.players[payer]
    pool = max(0, player.mana.get(color, 0))
    units = sum(1 for u in player.mana_units if u.sym == color and casting.spend_allowed(u.only, None))
    sources = sum(max((option.count(color) for option in source.options), default=0)
                  for source in casting.mana_sources(plan.state, payer, plan.info)
                  if not source.card_id.startswith(mana_units.PREFIX))
    return pool + units + sources


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import casting, effects, mana, optional_payment, paid_x

    ctx, info = d.resume['ctx'], d.resume['choose_x']
    bind, payer, color = info['bind'], info['payer'], info['color']
    if chosen[0] == 'pass':
        paid_x._record(ctx, bind, False, 0)
        effects.continue_effects(plan, ctx)
        return
    n = int(chosen[0])
    if n == 0:
        paid_x._record(ctx, bind, True, 0)
        effects.continue_effects(plan, ctx)
        return
    if n > _available_upper_bound(plan, payer, color):
        raise ActionError(f"You can't pay {n} {{{color}}}")
    # NUMBER input is bounded and affordable before either expansion happens.
    text = f'{{{color}}}' * n
    mana_cost = mana.ManaCost(colored=(color,) * n)
    if not casting.can_pay(plan.state, payer, mana_cost, plan.info):
        raise ActionError(f"You can't pay {n} {{{color}}}")
    cost = optional_payment.parse(text)
    assert cost is not None
    why = optional_payment.problem(plan, ctx, cost, payer)
    if why is not None:
        raise ActionError(f"You can't pay {n} {{{color}}}: {why}")
    ctx.setdefault('paid_x', {})[bind] = n
    optional_payment._pay(plan, ctx, {'cost': text, 'bind': bind, 'payer': payer, 'chosen': {},
                                    'amount_label': f'{n} {{{color}}}'}, cost)
