"""A selected fixed creature-counter cost may precede a sacrifice of its holder."""

from __future__ import annotations

from dataclasses import replace

from app.game.errors import ActionError
from app.game.rules_state import ObjectRef
from app.game.state import CardInstance
from app.rules import costs as C
from app.rules.plan import Plan

TEXT = "Remove a counter from a creature you control"


def index(cost: C.AbilityCost) -> int | None:
    counters = [(i, c) for i, c in enumerate(cost.components) if c.kind == C.REMOVE_COUNTER]
    if len(counters) != 1:
        return None
    i, part = counters[0]
    return (
        i
        if (
            part.text == TEXT
            and part.selector is not None
            and part.counter == C.ANY_COUNTER
            and part.amount == 1
            and not part.x
            and not part.among
            and not part.more
        )
        else None
    )


def preflight(cost: C.AbilityCost) -> C.AbilityCost:
    # Sacrifice eligibility can change when that exact counter is removed. The chooser
    # checks each fixed sacrifice against the native counter-first preview instead.
    return replace(cost, components=tuple(c for c in cost.components if not fixed_sacrifice(c)))


def fixed_sacrifice(part: C.CostComponent) -> bool:
    return part.kind == C.SACRIFICE and part.selector is not None and not part.anyn and not part.x


def preview(plan: Plan, cost: C.AbilityCost, chosen: dict[int, list[str]]) -> Plan:
    from app.rules import cost_payment, counter_removal_results

    i = index(cost)
    if i is None or len(chosen.get(i, [])) != 1:
        raise ActionError("The counter-first cost has no selected counter")
    token = chosen[i][0]
    cid = token.rsplit(":", 2)[0]
    tokens = cost_payment.counter_tokens(plan, [cid])
    if token not in tokens:
        raise ActionError("The selected counter can no longer pay the cost")
    holder, kind = tokens[token]
    trial = Plan(plan.state, plan.actor, plan.info, None)
    trial.excluded, trial.x_choice = plan.excluded, plan.x_choice
    if counter_removal_results.remove(trial, holder, kind, 1, by=plan.actor) != 1:
        raise ActionError("The selected counter can no longer pay the cost")
    return trial


def capture(plan: Plan, cost: C.AbilityCost, chosen: dict[int, list[str]]) -> list[ObjectRef]:
    i = index(cost)
    if i is None or len(chosen.get(i, [])) != 1:
        raise ActionError("The counter-first cost has no selected counter")
    cid = chosen[i][0].rsplit(":", 2)[0]
    card = plan.state.cards[cid]
    return [ObjectRef(card=cid, object_id=plan.oid(card), zone=card.zone)]


def guard(
    plan: Plan,
    cost: C.AbilityCost,
    card: CardInstance,
    chosen: dict[int, list[str]],
    original: list[ObjectRef] | None,
) -> None:
    from app.rules import cost_payment

    guard_original(plan, original)
    expected = capture(plan, cost, chosen)
    if original != expected:
        raise ActionError("The selected counter holder is no longer the original object")
    assert original is not None
    holder = plan.state.cards[original[0].card]
    if holder.controller != plan.actor or not plan.in_game(holder) or "Creature" not in plan.ch(holder).types:
        raise ActionError("The selected counter holder is no longer a creature you control")
    trial = preview(plan, cost, chosen)
    for i, part in enumerate(cost.components):
        if fixed_sacrifice(part):
            candidates = cost_payment.candidates(trial, part, plan.actor, trial.state.cards[card.id])
            if any(cid not in candidates for cid in chosen.get(i, [])):
                raise ActionError("The selected sacrifice cannot pay after the counter is removed")


def guard_original(plan: Plan, original: list[ObjectRef] | None) -> None:
    if original is None:
        raise ActionError(
            "This older payment did not save the original counter holder; cancel and pay it manually"
        )
    if len(original) != 1:
        raise ActionError("The counter-first payment needs its exact original counter holder")
    ref = original[0]
    current = plan.state.cards.get(ref.card)
    if current is None or plan.oid(current) != ref.object_id or current.zone != ref.zone:
        raise ActionError("The selected counter holder is no longer the original object")
