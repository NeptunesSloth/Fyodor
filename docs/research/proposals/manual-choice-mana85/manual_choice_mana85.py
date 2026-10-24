"""Legal manual mana-cost choices may open an optional payment's activation window."""
from __future__ import annotations

from app.rules.plan import Plan


def available(plan: Plan, payer: str, exclude: tuple[str, ...] = ()) -> bool:
    from app.rules import casting, cost_payment
    from app.rules.costs import parse_ability_cost

    for cid in plan.state.zones.get(f'{payer}:battlefield', []):
        card = plan.state.cards[cid]
        if cid in exclude or card.controller != payer or not plan.in_game(card):
            continue
        ch = plan.ch(card)
        for _, ability in casting.mana_abilities(plan.state, card, plan.info):
            if not ability.chooses or not ability.extra_cost or not any(ability.options) \
                    or not casting.spend_allowed(ability.spend_only, None):
                continue
            if ability.tap and not casting.can_use_tap_abilities(plan.state, card, ch, plan.info):
                continue
            # No claim about paying an activation's own mana input or which
            # objects to consume: this is an opportunity for a native manual activation.
            if not casting.mana_activation_cost(plan.state, card, ch, ability, plan.info).is_free:
                continue
            cost = parse_ability_cost(ability.extra_cost, card_name=ch.name)
            was, plan.excluded = plan.excluded, plan.excluded | frozenset(exclude)
            try:
                if casting.additional_problem(plan, cost, card, payer) is None \
                        and cost_payment.problem(plan, cost, card, payer) is None:
                    return True
            finally:
                plan.excluded = was
    return False
