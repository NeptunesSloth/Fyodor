"""Exact public-exile counter costs from a combat-damaged player's cards."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'exiled_counter_payment43'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text != ('You may remove a hit counter from a card that player owns in exile. '
                'If you do, draw a card and create two Treasure tokens.'):
        return None
    return ([{'do': STEP}], None, False)


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects
    from app.rules.plan import decide

    owners = set(effects._players(plan, ctx, 'event_player'))
    refs = [ref for c in plan.state.cards.values() if c.owner in owners and c.zone.endswith(':exile')
            and not c.face_down and not c.is_token and c.counters.get('hit', 0) > 0
            and (ref := context.ref_of(plan, c.id)) is not None]
    if not refs:
        return True
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Remove a hit counter to draw a card and create two Treasures?',
           options=[DecisionOption(id='decline', label='Decline'), DecisionOption(id='pay', label='Pay')],
           resume={'step': STEP, 'ctx': ctx, 'objects': [r.model_dump(mode='json') for r in refs]})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, counter_removal_results, effects, scripts
    from app.rules.plan import decide

    r = d.resume
    if not r.get('selecting'):
        if chosen == ['decline']:
            effects.continue_effects(plan, r['ctx'])
            return
        if chosen != ['pay']:
            raise ActionError('Choose whether to pay')
        refs = [ObjectRef.model_validate(raw) for raw in r['objects']]
        decide(plan, player=d.player, kind='choose_one', prompt='Choose a card in exile with a hit counter',
               options=[DecisionOption(id=ref.card, label=plan.state.cards[ref.card].name or 'Card', card_id=ref.card) for ref in refs],
               resume={**r, 'selecting': True})
        return
    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError('Choose an offered card')
    ref = next(ObjectRef.model_validate(raw) for raw in r['objects'] if raw['card'] == chosen[0])
    card = context._same(plan, ref)
    if card is None or not card.zone.endswith(':exile') or card.face_down or card.counters.get('hit', 0) < 1:
        effects.continue_effects(plan, r['ctx'])
        return
    if counter_removal_results.remove(plan, card.id, 'hit', 1, by=d.player) != 1:
        raise ActionError('The hit counter cannot pay this cost')
    parsed = scripts.parse_effects('Draw a card. Create two Treasure tokens.')
    assert parsed is not None
    ctx = r['ctx']
    ctx['effects'][ctx['next']:ctx['next']] = parsed[0]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP: start}
RESUME = {STEP: resume}
