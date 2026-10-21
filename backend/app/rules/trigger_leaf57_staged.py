"""Exact suspected designation removal and untargeted enchantment return cost."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.effects import Context
    from app.rules.plan import Plan
LAMMASU = "When this creature enters, all suspected creatures are no longer suspected."
DRAKE = "When this creature enters, sacrifice it unless you return an enchantment to its owner's hand."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != "triggered" or ability.text not in (LAMMASU, DRAKE):
        return None
    from app.rules import scripts, selectors

    native = scripts.define(replace(ability, text="When this creature enters, you gain 1 life."), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    if ability.text == LAMMASU:
        out["effects"] = [{"do": "lammasu_unsuspect57"}]
    else:
        out["effects"] = [
            {
                "do": "player_chooses",
                "who": "you",
                "any": True,
                "sel": selectors.Selector(types=("Enchantment",)).key(),
                "n": 1,
                "upto": True,
                "optional": True,
                "as": "returned57",
                "label": "enchantment to return",
            },
            {
                "do": "bounce",
                "who": "ref:returned57|" + selectors.Selector(types=("Enchantment",)).key(),
                "did": "return_cost57",
            },
            {"do": "only_if", "cond": {"succeeded": "return_cost57", "negate": True}, "skip": 1},
            {"do": "sacrifice", "who": "self"},
        ]
    return out


def unsuspect(plan: Plan, ctx: Context, effect: dict[str, Any]) -> bool:
    cards = [
        c
        for c in plan.state.cards.values()
        if c.zone.endswith(":battlefield")
        and plan.in_game(c)
        and plan.ch(c).is_creature
        and plan.oid(c) in plan.rules.suspected
    ]
    remove = {plan.oid(c) for c in cards}
    plan.rules.suspected[:] = [oid for oid in plan.rules.suspected if oid not in remove]
    for card in cards:
        for marker in list(card.effects):
            if marker.name == "Suspected":
                plan.do(
                    {"type": "remove_effect", "card_ids": [card.id], "effect_id": marker.id},
                    actor=ctx["controller"],
                )
    return True
