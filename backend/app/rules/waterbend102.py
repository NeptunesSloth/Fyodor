"""CR701.67: pay only the waterbend portion with explicit, nonmana taps."""

from __future__ import annotations

import re
from typing import Any

_NUMBER = re.compile(r"^(?:waterbend|tapbend) \{(\d+|X)\}$", re.IGNORECASE)
_MANDATORY = re.compile(r"^As an additional cost to cast this spell, waterbend \{(\d+|X)\}\.", re.IGNORECASE)


def part(text: str) -> Any:
    from app.rules import costs as C

    match = _NUMBER.fullmatch(text.strip())
    if match is None:
        return None
    amount = match[1]
    return C.CostComponent(
        C.WATERBEND,
        amount=0 if amount.upper() == "X" else int(amount),
        selector=C._selector("untapped creature you control" if text.lower().startswith("tapbend") else "untapped artifact or creature you control", zone="battlefield"),  # (wave 110C: "Tapbend" is Heirloom Epic's creature-only payment, not a waterbend)
        x=amount.upper() == "X",
        text=text,
    )


def mana(ch: Any) -> Any:
    from app.rules import mana as M

    symbols = "".join(
        "{" + match[1] + "}"
        for ability in ch.abilities
        if (match := _MANDATORY.match(ability.text)) is not None
    )
    return M.parse_cost(symbols)


def tapped(cost: Any, objects: dict[int, list[str]]) -> list[str]:
    from app.rules import costs as C

    return [
        cid
        for i, component in enumerate(cost.components if cost else ())
        if component.kind == C.WATERBEND
        for cid in objects.get(i, [])
    ]


def due(cost: Any, more: Any, objects: dict[int, list[str]]) -> Any:
    from app.game.errors import ActionError

    count = len(tapped(more, objects))
    if count > cost.generic:
        raise ActionError(
            "Choose fewer waterbend taps: they cannot pay colored mana or exceed the final generic cost"
        )
    return cost.plus_generic(-count)


def record(plan: Any, a: Any, more: Any, objects: dict[int, list[str]], payment: Any) -> None:
    from app.game.rules_state import CostContribution
    from app.rules import costs as C
    from app.rules import mana as M

    paid = any(c.kind == C.WATERBEND for c in more.components) if more else False
    payment.waterbend_paid102 = paid
    payment.x = a.x_value
    ids = tapped(more, objects)
    if ids:
        payment.total_cost = M.parse_cost(payment.total_cost).plus_generic(len(ids)).text()
        payment.contributions += [
            CostContribution(
                kind="waterbend",
                card=cid,
                object_id=plan.oid(cid),
                name=plan.state.cards[cid].name or "",
                pays="1",
                card_types=sorted(plan.ch(plan.state.cards[cid]).types),
            )
            for cid in ids
        ]


def hint(state: Any, player: str, card: Any, ch: Any, info: Any, cost: Any) -> Any:
    from app.rules import cost_payment
    from app.rules.plan import Plan

    view = Plan.view(state, player, info)
    maximum = 0
    for ability in ch.abilities:
        if (match := _MANDATORY.match(ability.text)) is not None and match[1].isdigit():
            component = part("Waterbend {" + match[1] + "}")
            maximum += min(int(match[1]), len(cost_payment.candidates(view, component, player, card)))
    return cost.plus_generic(-min(maximum, cost.generic))


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    # Put the nonzero-X declaration after the timing suffix so the native
    # activated parser retains both independent restrictions.
    if (ability.cost or "") != "Waterbend {X}":
        return None
    match = re.fullmatch(r"(.+) X can't be 0\. (Activate only [^.]+\.)", ability.text)
    if match is None:
        return None
    from dataclasses import replace

    from app.rules import scripts

    return scripts.define(replace(ability, text=match[1] + " " + match[2] + " X can't be 0."), ch)
