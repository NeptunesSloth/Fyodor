"""Native exact top-graveyard activation costs with deferred actual-top payment."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.game.actions import ActivateAbility
    from app.game.rules_state import Decision, PaymentRecord
    from app.game.state import CardInstance
    from app.rules.casting import Purpose
    from app.rules.costs import AbilityCost, CostComponent
    from app.rules.mana import ManaCost
    from app.rules.plan import Plan

KIND = 'EXILE_TOP_OWN_GY'
TEXT = 'Exile the top card of your graveyard'


def component(part: str) -> CostComponent | None:
    from app.rules.costs import CostComponent

    return CostComponent(KIND, text=part) if part == TEXT else None


def has(cost: AbilityCost) -> bool:
    return any(comp.kind == KIND for comp in cost.components)


def top(plan: Plan, player: str) -> str:
    pile = plan.state.zones.get(zone_key(player, 'graveyard'), [])
    if not pile:
        raise ActionError('Your graveyard has no top card to exile for this activation cost')
    return pile[-1]


def offer_order(plan: Plan, then: dict[str, Any]) -> bool:
    from app.rules import graveyard_order

    if not graveyard_order.offer(plan):
        return False
    d = plan.rules.decision
    assert d is not None and d.resume is not None
    d.resume['step'] = 'fixed_top_cost_order46'
    d.resume['fixed_top_then'] = then
    return True


def resume_order(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules import graveyard_order, replace

    assert d.resume is not None
    graveyard_order.resume(plan, d, chosen)
    replace.run_then(plan, d.resume['fixed_top_then'])


def pay(plan: Plan, source: CardInstance, record: PaymentRecord) -> None:
    """Reuse real exile-cost settlement/facts after binding the current actual top."""
    from app.rules import cost_payment, costs, selectors

    cid = top(plan, plan.actor)
    selector = selectors.Selector(card=True, zones=('graveyard',), zone_owner='you').key()
    native = costs.AbilityCost(components=(costs.CostComponent(costs.EXILE_FROM_GRAVEYARD, selector=selector, text=TEXT),))
    cost_payment.pay(plan, native, source, {0: [cid]}, record)


def offer_mana_window(plan: Plan, action: ActivateAbility, due: ManaCost, what: str, *, exclude: tuple[str, ...],
                      purpose: Purpose, then: dict[str, Any]) -> None:
    """CR601.2f–g /118.5 window, including surplus and reduced-{0}."""
    from app.rules import casting

    resume = {'step': 'pay_mana', 'intent': action.model_dump(mode='json', exclude={'r', 'actor', 'ts'}),
              'exclude': list(exclude), 'cost': due.text(), 'what': what, 'fixed_top_cost_window46': True,
              'paid_then': then, 'paid_purpose': casting._PURPOSE.dump_python(purpose, mode='json'),
              'paid_life_due': 2 * len(action.life_symbols or ()), 'x_payment': purpose.x_payment,
              'payment_context': casting._purpose_context(purpose)}
    casting.ask_to_tap(plan, due, what, resume)


def refresh_mana_window(plan: Plan) -> bool:
    """Never automatically close the explicitly requested cost preparation window."""
    from app.rules import casting, mana

    d = plan.rules.decision
    if d is None or not (d.resume or {}).get('fixed_top_cost_window46'):
        return False
    assert d.resume is not None
    then = d.resume.get('paid_then') or {}
    components = ((then.get('payload') or {}).get('cost') or {}).get('components') or []
    if (d.resume.get('step') != 'pay_mana' or then.get('stage') != 'activation_announced'
            or not any(c.get('kind') == KIND for c in components)):
        raise ActionError('The fixed-top cost mana window does not match its announced activation')
    d.display = casting._tap_display(plan, d.player, mana.parse_cost(d.resume['cost']), d.resume['what'], d.resume)
    return True
