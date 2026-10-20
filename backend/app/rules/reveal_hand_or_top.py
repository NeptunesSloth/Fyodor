"""Choose a hidden hand card or the library's top card, reveal, then enter if a creature."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import Decision, DecisionOption, ObjectRef
from app.rules import context

if TYPE_CHECKING:
    from app.rules.plan import Plan

_TEXT = ('Reveal a card from your hand or the top card of your library. '
         'If you reveal a creature card this way, put it onto the battlefield.')


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip() == _TEXT:
        return [{'do': 'reveal_hand_or_top_creature'}], None, False
    return None


def begin(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    pid = ctx['controller']
    if pid not in plan.live():
        return True
    options: list[DecisionOption] = []
    refs: dict[str, Any] = {}
    for cid in plan.state.zones.get(f'{pid}:hand', []):
        ref = context.ref_of(plan, cid)
        if ref is not None:
            key = f'hand:{cid}'
            options.append(DecisionOption(id=key, label=plan.state.cards[cid].name or 'Card', card_id=cid))
            refs[key] = ref.model_dump(mode='json')
    library = plan.state.zones.get(f'{pid}:library', [])
    if library and (ref := context.ref_of(plan, library[0])) is not None:
        options.append(DecisionOption(id='top', label='Top card of your library'))
        refs['top'] = ref.model_dump(mode='json')
    if not options:
        return True
    decide(plan, player=pid, kind='choose_one', prompt='Reveal a card from your hand or the top of your library',
           options=options, resume={'step': 'reveal_hand_or_top_creature', 'ctx': ctx, 'refs': refs},
           source=plan.state.cards.get(ctx.get('source_card') or ''))
    return False


def resume(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules import effects

    assert d.resume is not None
    ctx = d.resume['ctx']
    ref = ObjectRef.model_validate(d.resume['refs'][chosen[0]])
    card = context._same(plan, ref)
    if chosen[0] == 'top' and (not card or plan.state.zones.get(f'{d.player}:library', [])[:1] != [card.id]):
        card = None
    if card is not None:
        plan.do({'type': 'reveal', 'card_ids': [card.id]}, actor=d.player)
        if plan.ch(card).is_creature and not effects._return_cards(plan, ctx, {'to': 'battlefield', 'under': 'you'}, [card.id]):
            return
    effects.continue_effects(plan, ctx)


PRIMITIVES = {'reveal_hand_or_top_creature': begin}
RESUME = {'reveal_hand_or_top_creature': resume}
