"""Resolution-time hand and land counts for named-land mana production."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == 'triggered':
        return tap_definition(text)
    if ability.kind == 'activated' and text == 'Reveal your hand: If you have seven or more land cards in your hand, flip ~.':
        base = scripts.define(replace(ability, text='{0}: Flip ~.'), ch)
        if base is not None:
            return {**base, 'effects': [{'do': 'flip_if_seven_hand_lands', 'effects': base['effects']}]}
    return None


def flip_if_seven(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    lands = sum(c.zone == ctx['controller'] + ':hand' and plan.ch(c).is_land for c in plan.state.cards.values())
    if lands >= 7:
        ctx['effects'][ctx['next']:ctx['next']] = e['effects']
    return True


PRIMITIVES = {'flip_if_seven_hand_lands': flip_if_seven}


def register_reveal(plan: Plan, ability: str, ids: list[str]) -> None:
    from app.game.rules_state import CostReveal
    from app.rules import context

    refs = []
    for cid in ids:
        ref = context.ref_of(plan, cid)
        if ref is None:
            continue
        existing = next((fact for facts in plan.rules.revealed_activation_costs.values() for fact in facts
                         if fact.object.object_id == ref.object_id), None)
        prior = existing.prior if existing is not None else list(plan.state.cards[cid].revealed_to)
        refs.append(CostReveal(object=ref, prior=prior))
    plan.rules.revealed_activation_costs[plan.oid(ability)] = refs


def refresh_reveals(plan: Plan) -> None:
    from app.game.state import ALL

    records = plan.rules.revealed_activation_costs
    departed = [oid for oid in records if not any(c.zone == 'stack' and plan.oid(c) == oid for c in plan.state.cards.values())]
    old = [fact for oid in departed for fact in records.pop(oid)]
    active = {fact.object.object_id for facts in records.values() for fact in facts}
    for fact in old:
        ref = fact.object
        card = plan.state.cards.get(ref.card)
        if ref.object_id in active or card is None or plan.oid(card) != ref.object_id or not card.zone.endswith(':hand'):
            continue
        if ALL in fact.prior:
            continue
        plan.do({'type': 'hide', 'card_ids': [card.id]})
        if fact.prior:
            plan.do({'type': 'reveal', 'card_ids': [card.id], 'to': fact.prior})


def tap_definition(text: str) -> dict[str, Any] | None:
    from app.rules import selectors

    if text == ('Whenever a land you control is tapped for mana, add an additional one mana of any type that land produced '
                'for each other land you control with the same name as it.'):
        return {'kind': 'triggered', 'trigger': 'tap_for_mana', 'who': 'you',
                'sel': selectors.Selector(types=('Land',)).key(), 'extra': 'produced',
                'staged': True, 'same_name_count': True, 'effects': [], 'optional': False, 'target': None}
    return None
