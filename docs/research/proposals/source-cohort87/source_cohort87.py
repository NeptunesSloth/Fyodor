"""Exact source-plus-target activations retain one native target group and original source refs."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

RAZOR = "{8}: ~ and up to one other target creature each get +3/+3 until end of turn."
DANCER = "{R}{R}: ~ and another target creature each get +1/+0 until end of turn."
SUITOR = "When you attack with exactly two creatures, transform ~."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text in (RAZOR, DANCER):
        proxy = (
            "{8}: Up to one other target creature gets +3/+3 until end of turn."
            if text == RAZOR
            else "{R}{R}: Another target creature gets +1/+0 until end of turn."
        )
        native = scripts.define(replace(ability, text=proxy), ch)
        return (
            {
                **native,
                "effects": [
                    {"do": "source_cohort87"},
                    {
                        "do": "pump",
                        "who": "ref:source_cohort87",
                        "p": 3 if text == RAZOR else 1,
                        "t": 3 if text == RAZOR else 0,
                    },
                ],
            }
            if native
            else None
        )
    if text == SUITOR:
        native = scripts.define(
            replace(
                ability, text="When you attack with two or more creatures, transform ~."
            ),
            ch,
        )
        # The native declaration packet freezes the actual counted attackers.
        # This header qualification never reads later battlefield membership.
        return (
            {**native, "if": {"value": {"event_amount": 1}, "op": "==", "n": 2}}
            if native
            else None
        )
    return None


def cohort(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    cards = list(
        dict.fromkeys(
            effects._cards(plan, ctx, "self") + effects._cards(plan, ctx, "target")
        )
    )
    context.bind_objects(plan, ctx, "source_cohort87", cards)
    return True


PRIMITIVES = {"source_cohort87": cohort}
