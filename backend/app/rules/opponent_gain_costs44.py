"""Opponent-gain costs with persistent native payment stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, OpponentGainCostReceipt
from app.game.state import CardInstance
from app.rules import costs as C
from app.rules import mana as M
from app.rules import payment_continuations as pc
from app.rules.plan import Plan

KIND = 'OPPONENT_GAIN_LIFE'
STAGE = 'opponent_gain_costs44'


def definition(text: str) -> dict[str, Any] | None:
    from app.rules import conditions

    text = text.strip().rstrip('.').replace('~', 'this spell')
    text = text[:1].lower() + text[1:]
    if text != ("if you control a Forest, rather than pay this spell's mana cost, "
                'you may have an opponent gain 3 life'):
        return None
    condition = conditions.parse('you control a Forest')
    assert condition is not None
    return {'kind': 'static', 'static': 'alt_cost', 'cost': 'have an opponent gain 3 life',
            'cond': condition, 'effects': []}


def component(text: str) -> C.CostComponent | None:
    if text[:1].lower() + text[1:] != 'have an opponent gain 3 life':
        return None
    return C.CostComponent(KIND, amount=3, text=text)


def opponents(plan: Plan, payer: str) -> list[str]:
    from app.rules import cant_gain, effects

    return [pid for pid in effects._players(plan, {'controller': payer}, 'each_opponent')
            if cant_gain.why_not(plan, pid) is None]


def validate(plan: Plan, payer: str, recipient: str) -> None:
    if payer not in plan.live() or recipient not in opponents(plan, payer):
        raise ActionError('That opponent cannot gain life to pay this cost')


def problem(plan: Plan, cost: C.AbilityCost, payer: str) -> str | None:
    if any(c.kind == KIND for c in cost.components) and not opponents(plan, payer):
        return 'No opponent can gain life to pay this cost'
    return None


def choose(plan: Plan, action: A.CastSpell, index: int, part: C.CostComponent, card: CardInstance,
           given: list[str] | None, what: str) -> list[str] | None:
    from app.rules.plan import decide

    legal = opponents(plan, plan.actor)
    if given is not None:
        if len(given) != 1 or given[0] not in legal:
            raise ActionError('Choose one opponent who can gain life to pay this cost')
        return list(given)
    if not legal:
        raise ActionError('No opponent can gain life to pay this cost')
    if len(legal) == 1:
        return legal
    decide(plan, player=plan.actor, kind='choose_cards',
           prompt=f'{what}: choose an opponent to gain {part.amount} life',
           options=[DecisionOption(id=pid, label=plan.name(pid)) for pid in legal],
           min_choices=0, max_choices=1,
           resume={'step': 'ability_cost', 'component': index, 'amount': 1,
                   'intent': action.model_dump(mode='json', exclude={'r', 'actor', 'ts'})}, source=card)
    return None


def selected(plan: Plan, cost: C.AbilityCost, chosen: dict[int, list[str]]) -> list[GainLifeCost]:
    result = []
    for i, part in enumerate(cost.components):
        if part.kind != KIND:
            continue
        ids = chosen.get(i, [])
        if len(ids) != 1:
            raise ActionError('Choose one opponent to gain life to pay this cost')
        validate(plan, plan.actor, ids[0])
        result.append(GainLifeCost(plan.actor, ids[0], part.amount))
    return result


@dataclass(frozen=True)
class GainLifeCost:
    payer: str
    recipient: str
    nominal_amount: int


@dataclass
class GainLifeCosts:
    costs: list[GainLifeCost]
    then: dict[str, Any]
    payment: M.Payment | None = None
    next: int = 0
    pending: GainLifeCost | None = None
    receipts: list[OpponentGainCostReceipt] = field(default_factory=list)


def start(plan: Plan, frame: GainLifeCosts) -> None:
    """Own the continuation on both immediate completion and replacement pause."""
    from app.rules import replace

    while True:
        if frame.pending is not None:
            # Reached only after native gain completed, including a modified
            # zero/loss event. This records payment, never a life-total delta.
            frame.receipts.append(OpponentGainCostReceipt(recipient=frame.pending.recipient, nominal_amount=frame.pending.nominal_amount))
            frame.pending = None
        if frame.next >= len(frame.costs):
            payload = {**frame.then['payload'], 'opponent_gain_receipts': [
                {'recipient': r.recipient, 'nominal_amount': r.nominal_amount} for r in frame.receipts]}
            pc.finish(plan, {**frame.then, 'payload': payload}, frame.payment)
            return
        cost = frame.costs[frame.next]
        validate(plan, cost.payer, cost.recipient)
        frame.next += 1
        frame.pending = cost
        after = pc.continuation(plan, STAGE, frame)
        if not replace.gain_life(plan, [(cost.recipient, cost.nominal_amount)], actor=cost.payer, then=after):
            return


def resume(plan: Plan, frame: GainLifeCosts, payment: M.Payment | None) -> None:
    start(plan, frame)


pc.register(STAGE, GainLifeCosts, resume)
