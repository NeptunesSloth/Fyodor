"""Actual-object graveyard keyword costs granted for a fixed duration."""
from __future__ import annotations

from dataclasses import replace
from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts
    text = scripts.self_text(ability.text, ch.name)
    for keyword in ("embalm", "encore"):
        suffix = f"Target creature card in your graveyard gains {keyword} until end of turn. The {keyword} cost is equal to its mana cost."
        if ability.kind != "activated" or not text.endswith(": " + suffix):
            continue
        native = scripts.define(replace(ability, text=(ability.cost or "") + ": Return target creature card from your graveyard to your hand."), ch)
        if native is None:
            return None
        return {**native, "effects": [{"do": "graveyard_cost_grant57", "keyword": keyword}]}
    return None


def run(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import effects, layers, mana, scripts
    for cid in effects._cards(plan, ctx, "target"):
        card = plan.state.cards[cid]
        if card.zone != ctx["controller"] + ":graveyard" or card.owner != ctx["controller"]:
            continue
        ch = plan.ch(card)
        if "Creature" not in ch.types or not ch.mana_cost:
            continue
        cost = mana.parse_cost(ch.mana_cost)
        line = effect["keyword"].capitalize() + " " + ch.mana_cost + "."
        if cost.unsupported or scripts.granted_ability(line) is None:
            continue
        layers.add_effect(plan, affected=[plan.oid(card)], layer="6", source=ctx.get("source_object"),
                          controller=ctx["controller"], duration="end_of_turn", add_abilities=[line],
                          ability_zone="graveyard", label=line + " until end of turn")
    return True


PRIMITIVES = {"graveyard_cost_grant57": run}
