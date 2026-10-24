"""A selected fixed creature-counter cost may precede a sacrifice of its holder."""

from __future__ import annotations

from dataclasses import replace

from app.game.errors import ActionError
from app.game.rules_state import ObjectRef
from app.game.state import CardInstance
from app.rules import costs as C
from app.rules.plan import Plan

TEXT = "Remove a counter from a creature you control"
AMONG73 = "Remove three counters from among creatures you control"


def selected(extra: str | None) -> bool:
    return extra in (TEXT, AMONG73)


def index(cost: C.AbilityCost) -> int | None:
    counters = [(i, c) for i, c in enumerate(cost.components) if c.kind == C.REMOVE_COUNTER]
    selected_parts = [
        (i, part)
        for i, part in counters
        if (
            (
                (part.text == TEXT and part.amount == 1 and not part.among)
                or (part.text == AMONG73 and part.amount == 3 and part.among)
            )
            and part.selector is not None
            and part.counter == C.ANY_COUNTER
            and not part.x
            and not part.more
            and not part.anyn
        )
    ]
    if len(selected_parts) != 1:
        return None
    i, _ = selected_parts[0]
    others = [part for j, part in counters if j != i]
    # Hierophant Bio-Titan's actual optional counter reduction uses a disjoint
    # counter resource, including when its holder also pays the selected grant.
    if others and (
        len(others) != 1
        or any(fixed_sacrifice(part) for part in cost.components)
        or not all(
            part.text == "Remove any number of +1/+1 counters from among creatures you control"
            and part.anyn
            and part.among
            and part.counter == "+1/+1"
            and not part.x
            for part in others
        )
    ):
        return None
    return i


def preflight(cost: C.AbilityCost) -> C.AbilityCost:
    # Sacrifice eligibility can change when that exact counter is removed. The chooser
    # checks each fixed sacrifice against the native counter-first preview instead.
    return replace(cost, components=tuple(c for c in cost.components if not fixed_sacrifice(c)))


def fixed_sacrifice(part: C.CostComponent) -> bool:
    return part.kind == C.SACRIFICE and part.selector is not None and not part.anyn and not part.x


def preview(plan: Plan, cost: C.AbilityCost, chosen: dict[int, list[str]]) -> Plan:
    from app.rules import cost_payment, counter_removal_results

    i = index(cost)
    if i is None or len(chosen.get(i, [])) != cost.components[i].amount:
        raise ActionError("The counter-first cost has no exact selected counters")
    selected_tokens = [
        token
        for j, part in enumerate(cost.components)
        if part.kind == C.REMOVE_COUNTER
        for token in chosen.get(j, [])
    ]
    if len(set(selected_tokens)) != len(selected_tokens):
        raise ActionError("Each counter can pay only once")
    holders = list(dict.fromkeys(token.rsplit(":", 2)[0] for token in selected_tokens))
    tokens = cost_payment.counter_tokens(plan, holders)
    if any(token not in tokens for token in selected_tokens):
        raise ActionError("The selected counter can no longer pay the cost")
    trial = Plan(plan.state, plan.actor, plan.info, None)
    trial.excluded, trial.x_choice = plan.excluded, plan.x_choice
    from collections import Counter

    for (holder, kind), amount in Counter(tokens[token] for token in selected_tokens).items():
        if counter_removal_results.remove(trial, holder, kind, amount, by=plan.actor) != amount:
            raise ActionError("The selected counters can no longer pay the cost")
    return trial


def capture(plan: Plan, cost: C.AbilityCost, chosen: dict[int, list[str]]) -> list[ObjectRef]:
    i = index(cost)
    if i is None or len(chosen.get(i, [])) != cost.components[i].amount:
        raise ActionError("The counter-first cost has no exact selected counters")
    holders = dict.fromkeys(
        token.rsplit(":", 2)[0]
        for j, part in enumerate(cost.components)
        if part.kind == C.REMOVE_COUNTER
        for token in chosen.get(j, [])
    )
    return [ObjectRef(card=cid, object_id=plan.oid(cid), zone=plan.state.cards[cid].zone) for cid in holders]


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
    for ref in original:
        holder = plan.state.cards[ref.card]
        if (
            holder.controller != plan.actor
            or not plan.in_game(holder)
            or "Creature" not in plan.ch(holder).types
        ):
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
    if not original or len({ref.card for ref in original}) != len(original):
        raise ActionError("The counter-first payment needs its exact original counter holders")
    for ref in original:
        current = plan.state.cards.get(ref.card)
        if current is None or plan.oid(current) != ref.object_id or current.zone != ref.zone:
            raise ActionError("The selected counter holder is no longer the original object")


def retain_choice72(plan: Plan, cost: C.AbilityCost, chosen: dict[int, list[str]]) -> None:
    """Keep an automatic counter choice across a later nonmana-cost question."""
    i = index(cost)
    decision = plan.rules.decision
    if i is None or i not in chosen or decision is None or decision.resume is None:
        return
    decision.resume["counter_choice72"] = {
        "component": i,
        "tokens": list(chosen[i]),
        "originals": [ref.model_dump(mode="json") for ref in capture(plan, cost, chosen)],
    }
