"""CR 608.2g/707.12: ordinary costs for a cast allowed during resolution.

The saved pending effect is the authorization; no client flag grants permission.
The ordinary cast pipeline pays and records the selected cost and returns here
before priority, so alternatives need no duplicate payment implementation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.game import actions as A
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan


def active(state: Any, player: str, card_id: str) -> bool:
    r = state.rules
    p = r.free_cast_then if r else None
    return bool(p and p.get('card') == card_id and p.get('e', {}).get('paid') and (p.get('ctx', {}).get('controller') if p.get('e', {}).get('caster') != 'target110e' else p['ctx']['targets'][0]['id']) == player  # (wave 110E: Word of Command)
                and card_id in r.free_casts and card_id in state.cards and state.cards[card_id].zone != 'stack')


def alternatives(plan: Plan, card: CardInstance, ch: Characteristics, *, player: str | None = None) -> list[Any]:
    from app.rules import alt_costs, casting

    pid = player or plan.actor
    return [o for o in alt_costs.offers(plan.state, pid, card, ch, plan.info)
            if casting.additional_problem(plan, o.alt.cost, card, pid) is None]


def announce(plan: Plan, a: A.CastSpell, card: CardInstance, ch: Characteristics) -> bool:
    from app.rules import alt_costs, casting, mana
    from app.rules.plan import decide

    if a.free or not active(plan.state, plan.actor, card.id):
        return False  # old saved free=True paid casts retain their original supported path
    pending = plan.rules.free_cast_then
    assert pending is not None
    if pending.get('e', {}).get('effect_mana_cost') is not None:
        # 118.9: the resolving effect mandates this alternative, not the
        # ordinary mana cost or another alternative printed on the copy.
        pending['paid_cost_chosen'] = True
        if a.x_value is None and mana.parse_cost(ch.mana_cost).x:
            a.x_value = 0
        return False
    if not pending.get('paid_cost_chosen'):
        offers = alternatives(plan, card, ch)
        if offers:
            options = ([DecisionOption(id='normal', label=f'Pay its mana cost ({ch.mana_cost})')] if ch.mana_cost else [])
            options += [DecisionOption(id=o.key, label=o.label) for o in offers]
            options.append(DecisionOption(id='cancel', label='Back to copy selection'))
            decide(plan, player=plan.actor, kind='choose_one', prompt=f'{ch.name}: choose how to pay its cost (118.9).',
                   options=options, resume={'step': 'paid_effect_cost', 'intent': a.model_dump(mode='json', exclude={'r', 'actor', 'ts'})}, source=card)
            return True
        pending['paid_cost_chosen'] = True
    if casting.announce_free_optional(plan, a, card, ch):
        return True
    alt = alt_costs.chosen(plan, a.alt_cost, card, ch) if a.alt_cost is not None else None
    base = alt.alt.mana_cost if alt else mana.parse_cost(ch.mana_cost)
    if a.x_value is None and base.x:
        return casting.announce_free_x(plan, a, card, ch)
    if a.x_value is None and mana.parse_cost(ch.mana_cost).x:
        a.x_value = 0  # 107.3b: an alternative without X fixes the mana-cost X at zero
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules import casting, permissions

    intent = A.CastSpell.model_validate(d.resume['intent'])
    if chosen == ['cancel']:
        permissions.free_cast_done(plan, intent.card_id, cast=False)
        return
    pending = plan.rules.free_cast_then
    if pending is None or pending.get('card') != intent.card_id:
        return
    pending['paid_cost_chosen'] = True
    intent.alt_cost = None if chosen == ['normal'] else chosen[0]
    casting.cast_spell(plan, intent)


RESUME = {'paid_effect_cost': resume}
