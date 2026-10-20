"""Exact upkeep exile payments with native effect completion receipts."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'graveyard_payment45'
FINISH = 'graveyard_payment_finish45'
BIND = '_graveyard_payment45'


class ExilePayment(BaseModel):
    payer: str
    original: ObjectRef
    accepted: bool = True
    completed: bool = False
    result: list[ObjectRef] = Field(default_factory=list)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip()
    text = text[:1].upper() + text[1:]
    forms = {
        'Exile a creature card from your graveyard. If you do, put a +1/+1 counter on ~. Otherwise, sacrifice it.': 'troll',
        "You may exile a creature card from a graveyard. If you do, put a +1/+1 counter on ~. If you don't, tap ~.": 'feaster',
    }
    mode = forms.get(text)
    if mode is None:
        return None
    return ([{'do': STEP, 'mode': mode}], None, False)


def _outcome(ctx: dict[str, Any], mode: str, accepted: bool) -> None:
    from app.rules import scripts

    body = ('Put a +1/+1 counter on ~.' if accepted else
            'Sacrifice ~.' if mode == 'troll' else 'Tap ~.')
    parsed = scripts.parse_effects(body)
    assert parsed is not None
    at = int(ctx['next'])
    ctx['effects'] = [*ctx['effects'][:at], *parsed[0], *ctx['effects'][at:]]


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context
    from app.rules.plan import decide

    refs = []
    for card in plan.state.cards.values():
        if (card.is_token or not card.zone.endswith(':graveyard') or not plan.ch(card).is_creature
                or e['mode'] == 'troll' and card.zone != f"{ctx['controller']}:graveyard"):
            continue
        ref = context.ref_of(plan, card.id)
        if ref is not None:
            refs.append(ref)
    if not refs:
        _outcome(ctx, e['mode'], False)
        return True
    decide(plan, player=ctx['controller'], kind='choose_cards', prompt='Choose a creature card to exile',
           options=[DecisionOption(id=r.card, label=plan.state.cards[r.card].name or 'Creature card', card_id=r.card) for r in refs],
           min_choices=1 if e['mode'] == 'troll' else 0, max_choices=1,
           resume={'step': STEP, 'ctx': ctx, 'mode': e['mode'], 'objects': [r.model_dump(mode='json') for r in refs]})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    raw = d.resume
    ctx, mode = raw['ctx'], raw['mode']
    if len(chosen) > 1 or (not chosen and mode == 'troll') or any(cid not in {o.id for o in d.options} for cid in chosen):
        raise ActionError('Choose the required creature card')
    if not chosen:
        _outcome(ctx, mode, False)
        effects.continue_effects(plan, ctx)
        return
    ref = next(ObjectRef.model_validate(r) for r in raw['objects'] if r['card'] == chosen[0])
    card = context._same(plan, ref)
    if (card is None or card.is_token or not card.zone.endswith(':graveyard') or not plan.ch(card).is_creature
            or mode == 'troll' and card.zone != f"{ctx['controller']}:graveyard"):
        _outcome(ctx, mode, False)
        effects.continue_effects(plan, ctx)
        return
    # Acceptance precedes the native event. Completion is a distinct queued
    # boundary; neither acceptance nor its dependent instruction reads final zone.
    receipt = ExilePayment(payer=ctx['controller'], original=ref)
    ctx[BIND] = receipt.model_dump(mode='json')
    context.bind_objects(plan, ctx, BIND, [ref.card])
    at = int(ctx['next'])
    ctx['effects'] = [*ctx['effects'][:at],
                      {'do': 'exile', 'who': 'ref:' + BIND, 'from_zone': 'graveyard', 'as': BIND + '_result'},
                      {'do': FINISH, 'mode': mode}, *ctx['effects'][at:]]
    effects.continue_effects(plan, ctx)


def finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    receipt = ExilePayment.model_validate(ctx[BIND])
    if receipt.completed:
        raise ActionError('The exile payment already completed')
    receipt.result = context._object_refs(ctx, BIND + '_result')
    receipt.completed = True
    ctx[BIND] = receipt.model_dump(mode='json')
    _outcome(ctx, e['mode'], receipt.accepted)
    return True


PRIMITIVES = {STEP: start, FINISH: finish}
RESUME = {STEP: resume}
