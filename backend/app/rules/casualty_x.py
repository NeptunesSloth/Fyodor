"""CR 107.3a, 702.153a, 707.9: casualty X with a modified planeswalker copy.

Ob Nixilis's 2022-04-29 rulings: choose X; sacrifice power X OR GREATER.
The copy has starting loyalty X, even when the sacrificed creature was larger.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.actions import CastSpell
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

LINE = "Casualty X. The copy isn't legendary and has starting loyalty X"
PAGE = 100


def supported(line: str) -> bool:
    from app.rules.oracle import strip_reminders

    return strip_reminders(line).strip().rstrip('.') == LINE


def has(ch: Characteristics) -> bool:
    return any(ab.kind == 'keywords' and 'casualty' in ab.keywords and supported(ab.text) for ab in ch.abilities)


def announce(plan: Plan, a: CastSpell, card: CardInstance, ch: Characteristics, optional: list[Any], *, start: int = 0) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import casting, cost_changes, cost_payment
    from app.rules.plan import decide

    offer = next((o for o in optional if o.kind == 'casualty_x'), None)
    if offer is None or a.x_value is not None:
        return False
    comp = cost_changes.keyword_component(offer)
    candidates = cost_payment.candidates(plan, comp, plan.actor, card)
    most = max((cost_payment.power(plan.state.cards[c], plan.ch(plan.state.cards[c])) or 0 for c in candidates), default=0)
    options = [DecisionOption(id=f'x:{n}', label=str(n)) for n in range(start, min(start + PAGE, most + 1))]
    if start:
        options.append(DecisionOption(id=f'page:{max(0, start-PAGE)}', label='Previous values'))
    if start + PAGE <= most:
        options.append(DecisionOption(id=f'page:{start+PAGE}', label='More values'))
    decide(plan, player=plan.actor, kind='choose_one', prompt=f'{ch.name}: choose X for casualty (sacrifice power X or greater)',
           options=options, resume=casting._announcing(plan, 'casualty_x', a), source=card)
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules import casting, cost_changes
    from app.rules.engine import INTENTS

    if casting.cancelled(plan, d, chosen):
        return
    intent = A.parse_action(d.resume['intent'])
    assert isinstance(intent, A.CastSpell)
    plan.rules.priority = d.player
    plan.rules.passed = []
    if chosen[0].startswith('page:'):
        card = plan.state.cards[intent.card_id]
        ch = plan.ch(card)
        offers = cost_changes.chosen_optional(plan.state, d.player, card, ch, plan.info, intent.optional_costs)
        announce(plan, intent, card, ch, offers, start=int(chosen[0][5:]))
        return
    intent.x_value = int(chosen[0][2:])
    INTENTS[intent.type](plan, intent)
