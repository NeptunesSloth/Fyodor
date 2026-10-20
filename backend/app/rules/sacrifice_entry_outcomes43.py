"""Direct sacrifice-cost LKI and simultaneous native reanimation entry forms."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'sacrifice_blood43'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text == ('Create a Blood token. If you sacrificed an Angel this way, create a number of Blood tokens '
                'equal to its toughness instead.'):
        return ([{'do': STEP}], None, False)
    if text != ('Return each creature card from your graveyard to the battlefield with a finality counter on it. '
                'Those creatures are Vampires in addition to their other types.'):
        return None
    from app.rules import scripts

    returned = scripts.parse_effects('Return each creature card from your graveyard to the battlefield.')
    assert returned is not None and len(returned[0]) == 1
    return ([{**returned[0][0], 'counter': 'finality', 'entry_characteristics': {'add_subtypes': ['Vampire']}}], returned[1], False)


def blood(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import scripts
    from app.rules.plan import decide
    from app.rules.sba import toughness
    from app.rules.triggers import _snapshot_card

    sid = ctx.get('stack_id')
    paid = plan.rules.payments.get(plan.oid(sid)) if sid else None
    objects = paid.sacrificed_objects if paid is not None else []
    snap = plan.rules.lki.get(objects[0]) if len(objects) == 1 else None
    amount: int | None = None
    if snap is not None:
        card, ch = _snapshot_card(plan, snap)
        amount = 1 if 'Angel' not in ch.subtypes else toughness(card, ch)
    if amount is None:
        decide(plan, player=ctx['controller'], kind='manual_resolution',
               prompt='This save has no exact sacrificed-creature information. Resolve the Blood creation manually.',
               options=[DecisionOption(id='done', label='Done')], resume={'step': STEP, 'ctx': ctx})
        return False
    native = scripts.parse_effects('Create a Blood token.')
    assert native is not None and len(native[0]) == 1
    # Freeze the direct cost's LKI quantity before native token replacement can
    # pause. Copies use copying._payment_alias's original paid objects (707.10).
    ctx['effects'][ctx['next']:ctx['next']] = [{**native[0][0], 'n': max(0, amount)}]
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if chosen != ['done']:
        raise ActionError('Finish the manual resolution')
    effects.continue_effects(plan, d.resume['ctx'])


PRIMITIVES = {STEP: blood}
RESUME = {STEP: resume}
