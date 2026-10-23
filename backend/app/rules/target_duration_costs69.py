"""Will's target beneficiary and original duration controller are independent."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

FIRST = "Until your next turn, up to two target creatures each have base power and toughness 0/3 and lose all abilities."
SECOND = "Target player draws two cards. Until your next turn, instant, sorcery, and planeswalker spells that player casts cost {2} less to cast."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != "loyalty":
        return None
    body = ability.text.partition(":")[2].strip()
    if body == FIRST:
        return scripts.define(
            replace(
                ability,
                text=f"{ability.cost}: Up to two target creatures lose all abilities and have base power and toughness 0/3 until your next turn.",
            ),
            ch,
        )
    if body == SECOND:
        native = scripts.define(replace(ability, text=f"{ability.cost}: Target player draws two cards."), ch)
        return (
            {**native, "effects": [*native["effects"], {"do": "will_discount69"}]}
            if native is not None
            else None
        )
    return None


def discount(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import permissions

    key = permissions.spell_filter("instant, sorcery, or planeswalker")
    assert key is not None
    return permissions.cost_modifier(
        plan,
        ctx,
        {
            "do": "cost_modifier",
            "delta": -2,
            "filter": key,
            "until": "next_turn",
            "until_player69": ctx["controller"],
            "recipient66": "target",
        },
    )


PRIMITIVES = {"will_discount69": discount}
