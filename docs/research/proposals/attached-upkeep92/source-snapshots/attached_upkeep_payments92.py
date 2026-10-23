"""Attached-upkeep payments retain the original event player and damage prevention."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

AMOUNT = 'That player may pay any amount of mana. ~ deals 2 damage to that player. Prevent X of that damage, where X is the amount of mana that player paid this way.'
FIXED = "That player may pay {3}. If they don't, ~ deals 2 damage to that player and you tap that creature."
BIND = 'upkeep92'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip()
    if text.lower() == AMOUNT.lower():
        return ([{'do': 'upkeep_amount92'}, {'do': 'upkeep_prevent92'},
                 {'do': 'damage', 'who': 'event_player', 'n': 2}, {'do': 'upkeep_cleanup92'}], None, False)
    if text.lower() == FIXED.lower():
        return ([{'do': 'optional_payment', 'who': 'event_player', 'cost': '{3}', 'bind': BIND},
                 {'do': 'only_if', 'cond': {'succeeded': BIND, 'negate': True}, 'skip': 2},
                 {'do': 'damage', 'who': 'event_player', 'n': 2}, {'do': 'tap', 'who': 'event'}], None, False)
    return None


def amount(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import group_choice, optional_payment, paid_x
    from app.rules.plan import decide

    payer = optional_payment.payer_of(plan, ctx, 'event_player')
    if payer is None:
        paid_x._record(ctx, BIND, False, 0)
        return True
    decide(plan, player=payer, kind='choose_one', prompt=f"{ctx.get('name') or 'It'}: pay any amount of mana",
           options=[DecisionOption(id=group_choice.NUMBER, label='Type a number ≥ 0', group='number'),
                    DecisionOption(id='pass', label="Don't pay")],
           source=plan.state.cards.get(ctx.get('source_card') or ''),
           resume={'step': optional_payment.STEP, 'ctx': ctx, 'cost': '{0}', 'upkeep_amount92': True,
                   'payer': payer})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import casting, effects, mana, mana_units, optional_payment, paid_x

    ctx, payer = d.resume['ctx'], d.resume['payer']
    if chosen[0] == 'pass':
        paid_x._record(ctx, BIND, False, 0)
        effects.continue_effects(plan, ctx)
        return
    n = int(chosen[0])
    if n == 0:
        paid_x._record(ctx, BIND, True, 0)
        effects.continue_effects(plan, ctx)
        return
    player = plan.state.players[payer]
    # An upper bound only: the native solver still validates every restriction and payment.
    bound = sum(player.mana.values()) + len(player.mana_units)
    bound += sum(max((len(option) for option in source.options), default=0)
                 for source in casting.mana_sources(plan.state, payer, plan.info)
                 if not source.card_id.startswith(mana_units.PREFIX))
    cost = mana.parse_cost(f'{{{n}}}')
    purpose = casting.Purpose(selected_cost_has_x=False)
    if n > bound or not casting.can_pay(plan.state, payer, cost, plan.info, purpose=purpose):
        raise ActionError(f"You can't pay {{{n}}}; activate your mana abilities first")
    parsed = optional_payment.parse(f'{{{n}}}')
    assert parsed is not None
    ctx.setdefault('paid_x', {})[BIND] = n
    optional_payment._pay(plan, ctx, {'cost': f'{{{n}}}', 'bind': BIND, 'payer': payer,
                                    'chosen': {}, 'cost_has_x': False}, parsed)


def prevention(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import paid_x, replace

    n = paid_x.amount(ctx, BIND)
    if n:
        record = replace.add_record(plan, event='damage', match={'source': {'self': True}, 'to': {'players': 'any', 'objects': {}}},
                                    op={'do': 'finite_prevention', 'prevention': True, 'limit': n, 'allocate': True},
                                    controller=ctx['controller'], source=ctx.get('source_object'),
                                    source_card=ctx.get('source_card'), label=ctx.get('name') or 'Paid prevention')
        ctx['prevention92'] = record['id']
    return True


def cleanup(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    record = ctx.pop('prevention92', None)
    if record:
        plan.rules.replacements = [r for r in plan.rules.replacements if r.get('id') != record]
    return True


PRIMITIVES = {'upkeep_amount92': amount, 'upkeep_prevent92': prevention, 'upkeep_cleanup92': cleanup}
