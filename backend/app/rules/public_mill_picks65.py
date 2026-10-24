"""Bounded public-mill selections with actual hand outcomes and prepared commander choices."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_ROOM = 'Mill four cards, then return up to two permanent cards from among them to your hand.'
_NASHI = 'You mill that many cards. You may put any number of legendary and/or enchantment cards from among them into your hand. If you put no cards into your hand this way, put a +1/+1 counter on ~.'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().casefold()
    if text not in (_ROOM.casefold(), _NASHI.casefold()):
        return None
    nashi = text == _NASHI.casefold()
    seq: list[dict[str, Any]] = [{'do': 'mill', 'who': 'you', 'n': {'event_amount': 1} if nashi else 4, 'as': 'public_mill65'},
                               {'do': 'public_pick65', 'nashi': nashi}]
    if nashi:
        seq.append({'do': 'nashi_counter65'})
    return seq, None, False


def choose(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects, public_mill_attachment59
    from app.rules.plan import decide

    public_mill_attachment59.prepare_public_mill(plan, ctx, {'who': 'ref:public_mill65'})
    options = []
    for cid in effects._looked(plan, ctx)[1]:
        ch = plan.ch(plan.state.cards[cid])
        matches = 'Artifact' in ch.types if e.get('artifact66') else (('Legendary' in ch.supertypes or 'Enchantment' in ch.types) if e['nashi'] else ch.is_permanent_card)
        if matches:
            options.append(cid)
    ctx['returned65'] = []
    if not options:
        return True
    decide(plan, player=ctx['controller'], kind='choose_cards', prompt='Choose milled cards to return to your hand',
           options=[DecisionOption(id=cid, label=plan.state.cards[cid].name or 'Card', card_id=cid) for cid in options],
           min_choices=0, max_choices=1 if e.get('artifact66') else len(options) if e['nashi'] else min(2, len(options)),
           resume={'step': 'public_pick65', 'ctx': ctx, 'e': e})
    return False


def selected(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume['ctx']
    live = set(effects._looked(plan, ctx)[1])
    ctx['returned65'] = [{'card': cid, 'object': plan.oid(cid)} for cid in chosen if cid in live]
    finish(plan, ctx, d.resume['e'])


def finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules import effects, replacements
    from app.rules.plan import decide

    valid = set(effects._looked(plan, ctx)[1])
    picked = [r['card'] for r in ctx['returned65'] if r['card'] in valid and plan.oid(r['card']) == r['object']]
    for cid in picked:
        card = plan.state.cards[cid]
        key = f'{plan.oid(card)}>hand'
        if key not in plan.rules.answers_903_9b and replacements._commander_instead(plan, card, 'hand') is None:
            decide(plan, player=card.owner, kind='confirm', prompt=f'{card.name}: put it into the command zone instead of your hand?',
                   options=[DecisionOption(id='yes', label='Command zone'), DecisionOption(id='no', label='Into your hand')],
                   resume={'step': 'public_command65', 'ctx': ctx, 'e': e, 'key': key, 'card': cid},
                   memory_key=f'commander_zone:{card.commander_key}', memory_context='hand')
            return
    if picked:
        plan.do({'type': 'move', 'card_ids': picked, 'to': {'player': ctx['controller'], 'zone': 'hand'}}, actor=ctx['controller'])
    effects.continue_effects(plan, ctx)


def commander(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    if r['card'] in effects._looked(plan, r['ctx'])[1]:
        plan.rules.answers_903_9b[r['key']] = chosen[0]
    finish(plan, r['ctx'], r['e'])


def counter(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    returned = any((card := plan.state.cards.get(r['card'])) is not None
                   and card.zone == ctx['controller'] + ':hand' and plan.oid(card) != r['object'] for r in ctx['returned65'])
    return True if returned else effects.add_counters(plan, ctx, {'who': 'self', 'kind': '+1/+1', 'n': 1})


PRIMITIVES = {'public_pick65': choose, 'nashi_counter65': counter}
RESUME = {'public_pick65': selected, 'public_command65': commander}
