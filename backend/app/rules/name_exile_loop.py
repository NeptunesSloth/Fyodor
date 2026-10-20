"""CR 201.2 / 608.2c: exile until taking a card or repeating a name."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.cards.names import normalize_name
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'name_exile_loop'
_CURRENT = 'name_loop_current'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip() != ('Exile the top card of your library. You may put that card into your hand unless it has the same name as another card exiled this way. '
                        'Repeat this process until you put a card into your hand or you exile two cards with the same name, whichever comes first.'):
        return None
    return ([{'do': STEP}], None, False)


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    return _next(plan, ctx, [])


def _next(plan: Plan, ctx: dict[str, Any], seen: list[str]) -> bool:
    from app.rules import card_names, effects

    pid = ctx['controller']
    if not plan.state.zones.get(f'{pid}:library'):
        return True  # exiling from an empty library is not drawing from it
    effects.exile_top(plan, ctx, {'do': 'exile_top', 'n': 1, 'as': _CURRENT})
    found = effects._cards(plan, ctx, 'ref:' + _CURRENT)
    if not found:
        return True
    cid = found[0]
    card = plan.state.cards[cid]
    if not card.zone.endswith(':exile'):
        return True
    names = {normalize_name(n) for n in card_names.names_of(plan.ch(card))}
    if names & set(seen):
        plan.note(f"{ctx.get('name') or 'The effect'} stops: two exiled cards share a name", [cid])
        return True
    decide(plan, player=pid, kind='choose_one',
           prompt=f"{ctx.get('name') or 'Exile'}: put {plan.ch(card).name or 'this card'} into your hand, or continue?",
           options=[DecisionOption(id='take', label='Put into your hand', card_id=cid),
                    DecisionOption(id='continue', label='Continue exiling')],
           resume={'step': STEP, 'ctx': ctx, 'seen': sorted(set(seen) | names), 'card': cid, 'oid': plan.oid(card)})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if len(chosen) != 1 or chosen[0] not in {'take', 'continue'}:
        raise ActionError('Choose whether to take the card or continue')
    r, ctx = d.resume, d.resume['ctx']
    card = plan.state.cards.get(r['card'])
    if chosen[0] == 'take' and card is not None and card.zone.endswith(':exile') and plan.oid(card) == r['oid']:
        plan.do({'type': 'move', 'card_ids': [card.id], 'to': {'player': card.owner, 'zone': 'hand'}}, actor=d.player)
        effects.continue_effects(plan, ctx)
    elif _next(plan, ctx, r['seen']):
        effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP: start}
