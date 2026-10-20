"""Counter kinds and recipients chosen from actual returned object packets."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'returned_counter_choice42'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text == 'Noncreature spells your opponents cast cost {2} more to cast until your next turn.':
        from app.rules import permissions

        key = permissions.spell_filter('noncreature')
        assert key is not None
        return ([{'do': 'cost_modifier', 'delta': 2, 'caster': 'opponent', 'filter': key, 'until': 'next_turn'}], None, False)
    if text == ('Return target creature or planeswalker card from your graveyard to the battlefield. '
                'Put a +1/+1 counter or a loyalty counter on it.'):
        first = scripts.parse_effects('Return target creature or planeswalker card from your graveyard to the battlefield.')
        mode = 'kind'
    elif text == ('Return up to two target creature cards with total mana value 3 or less from your graveyard to the battlefield. '
                  'Put a deathtouch counter on either of them. Then put a menace counter on either of them.'):
        first = scripts.parse_effects('Return up to two target creature cards with total mana value 3 or less from your graveyard to the battlefield.')
        mode = 'recipient'
    else:
        return None
    if first is None or len(first[0]) != 1:
        return None
    tail = ([{'do': STEP, 'mode': 'kind', 'ref_count': '_returned_counter42'}] if mode == 'kind' else
            [{'do': STEP, 'mode': 'recipient', 'kind': kind, 'ref_count': '_returned_counter42'} for kind in ['deathtouch', 'menace']])
    return ([{**first[0][0], 'as': '_returned_counter42'}, *tail], first[1], False)


def choose(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context
    from app.rules.plan import decide

    raw = context.refs(ctx).get(e['ref_count']) or {}
    refs = [ObjectRef.model_validate(r) for r in raw.get('objects') or []]
    live = [ref for ref in refs if (card := context._same(plan, ref)) is not None
            and card.zone.endswith(':battlefield')]
    if not live:
        return True
    options = ([DecisionOption(id=k, label=f'Put a {k} counter') for k in ['+1/+1', 'loyalty']]
               if e['mode'] == 'kind' else
               [DecisionOption(id=r.card, label=plan.state.cards[r.card].name or 'Permanent', card_id=r.card) for r in live])
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Choose the counter kind' if e['mode'] == 'kind'
           else f'Choose a returned creature for the {e["kind"]} counter', options=options,
           resume={'step': STEP, 'ctx': ctx, 'e': e, 'objects': [r.model_dump(mode='json') for r in live]})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    r = d.resume
    ctx, e = r['ctx'], r['e']
    refs = [ObjectRef.model_validate(raw) for raw in r['objects']]
    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError('Choose one offered counter or recipient')
    kind = chosen[0] if e['mode'] == 'kind' else e['kind']
    selected = refs if e['mode'] == 'kind' else [ref for ref in refs if ref.card == chosen[0]]
    cards = [card.id for ref in selected if (card := context._same(plan, ref)) is not None
             and card.zone.endswith(':battlefield')]
    context.bind_objects(plan, ctx, '_returned_counter_recipient42', cards)
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do': 'add_counters', 'who': 'ref:_returned_counter_recipient42', 'kind': kind, 'n': 1}]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP: choose}
RESUME = {STEP: resume}
