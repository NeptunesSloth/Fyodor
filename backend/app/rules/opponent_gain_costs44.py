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
    prefix = "if you control a Forest, rather than pay this spell's mana cost, you may "
    payments = {'have an opponent gain 3 life', 'have each other player gain 5 life', 'have each other player gain 6 life'}
    if not text.startswith(prefix) or (payment := text[len(prefix):]) not in payments:
        return None
    condition = conditions.parse('you control a Forest')
    assert condition is not None
    return {'kind': 'static', 'static': 'alt_cost', 'cost': payment,
            'cond': condition, 'effects': []}


def component(text: str) -> C.CostComponent | None:
    normalized = text[:1].lower() + text[1:]
    if normalized == 'have an opponent gain 3 life':
        return C.CostComponent(KIND, amount=3, text=text)
    amounts = {'have each other player gain 5 life': 5, 'have each other player gain 6 life': 6}
    if normalized in amounts:
        return C.CostComponent(KIND, amount=amounts[normalized], text=text, gain_scope='each_other_player')
    return None


def all_others(plan: Plan, payer: str) -> list[str]:
    return [pid for pid in plan.apnap() if pid != payer and pid in plan.live()]


def validate_other(plan: Plan, payer: str, recipient: str) -> None:
    from app.rules import cant_gain

    if payer not in plan.live() or recipient not in all_others(plan, payer) or cant_gain.why_not(plan, recipient) is not None:
        raise ActionError('Every other player must be able to gain life to pay this cost')


def opponents(plan: Plan, payer: str) -> list[str]:
    from app.rules import cant_gain, effects

    return [pid for pid in effects._players(plan, {'controller': payer}, 'each_opponent')
            if cant_gain.why_not(plan, pid) is None]


def validate(plan: Plan, payer: str, recipient: str) -> None:
    if payer not in plan.live() or recipient not in opponents(plan, payer):
        raise ActionError('That opponent cannot gain life to pay this cost')


def problem(plan: Plan, cost: C.AbilityCost, payer: str) -> str | None:
    from app.rules import cant_gain

    for part in cost.components:
        if part.kind != KIND:
            continue
        if part.gain_scope == 'each_other_player':
            if any(cant_gain.why_not(plan, pid) is not None for pid in all_others(plan, payer)):
                return 'Every other player must be able to gain life to pay this cost'
        elif not opponents(plan, payer):
            return 'No opponent can gain life to pay this cost'
    return None


def choose(plan: Plan, action: A.CastSpell, index: int, part: C.CostComponent, card: CardInstance,
           given: list[str] | None, what: str) -> list[str] | None:
    from app.rules.plan import decide

    if part.gain_scope == 'each_other_player':
        legal = all_others(plan, plan.actor)
        for pid in legal:
            validate_other(plan, plan.actor, pid)
        if given is not None and (len(given) != len(legal) or set(given) != set(legal)):
            raise ActionError('This cost has every other player gain life; no recipient may be omitted')
        return legal
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
        if part.gain_scope == 'each_other_player':
            expected = all_others(plan, plan.actor)
            if ids != expected:
                raise ActionError('The original other-player cost recipients changed; cancel and announce again')
            for pid in ids:
                validate_other(plan, plan.actor, pid)
                result.append(GainLifeCost(plan.actor, pid, part.amount, f'all:{i}'))
            continue
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
    group: str | None = None


@dataclass
class GainLifeCosts:
    costs: list[GainLifeCost]
    then: dict[str, Any]
    payment: M.Payment | None = None
    next: int = 0
    pending: GainLifeCost | None = None
    pending_others: list[GainLifeCost] = field(default_factory=list)
    receipts: list[OpponentGainCostReceipt] = field(default_factory=list)


def start(plan: Plan, frame: GainLifeCosts) -> None:
    """Own the continuation on both immediate completion and replacement pause."""
    from app.rules import replace

    while True:
        if frame.pending is not None:
            # Reached only after native gain completed, including a modified
            # zero/loss event. This records payment, never a life-total delta.
            frame.receipts.append(OpponentGainCostReceipt(recipient=frame.pending.recipient, nominal_amount=frame.pending.nominal_amount))
            frame.receipts.extend(OpponentGainCostReceipt(recipient=c.recipient, nominal_amount=c.nominal_amount)
                                  for c in frame.pending_others)
            frame.pending_others = []
            frame.pending = None
        if frame.next >= len(frame.costs):
            payload = {**frame.then['payload'], 'opponent_gain_receipts': [
                {'recipient': r.recipient, 'nominal_amount': r.nominal_amount} for r in frame.receipts]}
            pc.finish(plan, {**frame.then, 'payload': payload}, frame.payment)
            return
        cost = frame.costs[frame.next]
        if cost.group is not None:
            from app.rules import life_changes44

            grouped = []
            while frame.next < len(frame.costs) and frame.costs[frame.next].group == cost.group:
                current = frame.costs[frame.next]
                validate_other(plan, current.payer, current.recipient)
                grouped.append(current)
                frame.next += 1
            frame.pending, frame.pending_others = grouped[0], grouped[1:]
            after = pc.continuation(plan, STAGE, frame)
            request = {'mode': 'gain_cost70', 'changes': [[c.recipient, c.nominal_amount] for c in grouped],
                       'actor': cost.payer, 'operation': replace._life_operation(plan, None)}
            if not life_changes44.change(plan, request, then=after):
                return
        else:
            validate(plan, cost.payer, cost.recipient)
            frame.next += 1
            frame.pending = cost
            after = pc.continuation(plan, STAGE, frame)
            if not replace.gain_life(plan, [(cost.recipient, cost.nominal_amount)], actor=cost.payer, then=after):
                return


def resume(plan: Plan, frame: GainLifeCosts, payment: M.Payment | None) -> None:
    start(plan, frame)


pc.register(STAGE, GainLifeCosts, resume)
