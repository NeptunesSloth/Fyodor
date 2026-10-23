"""Nightshade chooses its actual black-card count only during targeted resolution."""
from __future__ import annotations

from typing import Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef
from app.rules.plan import Plan, decide

TEXT = 'you may reveal X black cards in your hand. If you do, target creature gets -X/-X until end of turn.'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    if body.strip().lower() != TEXT.lower():
        return None
    base = scripts.parse_effects('Target creature gets -1/-1 until end of turn.')
    return ([{'do': 'nightshade_reveal88'}], base[1], False) if base is not None else None


def begin(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    refs = [context.ref_of(plan, c.id) for c in plan.state.cards.values()
            if c.zone == ctx['controller'] + ':hand' and 'B' in plan.ch(c).colors]
    rows = [r for r in refs if r is not None]
    if not rows:
        return True
    stack = context.ref_of(plan, ctx['stack_id'])
    if stack is None or stack.zone != 'stack':
        raise ActionError('The original Nightshade trigger is no longer resolving')
    decide(plan, player=ctx['controller'], kind='choose_cards', prompt='Nightshade Assassin: reveal any number of black cards',
           options=[DecisionOption(id=r.card, label=plan.ch(plan.state.cards[r.card]).name or 'Card', card_id=r.card) for r in rows],
           min_choices=0, max_choices=len(rows), resume={'step': 'nightshade_reveal88', 'ctx': ctx,
           'stack': stack.model_dump(mode='json'), 'rows': [r.model_dump(mode='json') for r in rows]})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects, mana_named_land_profiles

    refs = [ObjectRef.model_validate(r) for r in d.resume['rows']]
    stack = ObjectRef.model_validate(d.resume['stack'])
    if context._same(plan, stack) is None or stack.zone != 'stack' or any(context._same(plan, r) is None for r in refs):
        raise ActionError('The original trigger or hand cards changed during revelation')
    if len(chosen) != len(set(chosen)) or not set(chosen) <= {r.card for r in refs}:
        raise ActionError('Choose distinct original black hand cards')
    ctx = d.resume['ctx']
    if chosen:
        mana_named_land_profiles.register_reveal(plan, stack.card, chosen)
        plan.do({'type': 'reveal', 'card_ids': chosen})
        effects.pump(plan, ctx, {'who': 'target', 'p': -len(chosen), 't': -len(chosen)})
    effects.continue_effects(plan, ctx)


PRIMITIVES = {'nightshade_reveal88': begin}
RESUME = {'nightshade_reveal88': resume}
