"""-- aura guard (wave 110C) -- "If enchanted land would be destroyed, instead sacrifice this Aura and that land gains indestructible until end of turn."

A destruction replacement (614.1a) on an Aura, applied beside umbra armor (regeneration.umbra_armor / use_umbra_armor, which every destroy
path and the lethal-damage SBA already call). 701.17a: sacrifice = put into its owner's graveyard; 702.12b: the land then can't be destroyed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

TEXT = "If enchanted land would be destroyed, instead sacrifice this Aura and that land gains indestructible until end of turn."


def definition(ability: AbilityText) -> dict[str, Any] | None:
    return {"kind": "static", "static": "sac_aura_instead110c", "effects": []} if ability.text == TEXT else None


def guards(plan: Plan, aura: CardInstance) -> bool:
    from app.rules import scripts

    return any(d.get("static") == "sac_aura_instead110c" for d in scripts.definitions(plan.ch(aura)).values())


def use(plan: Plan, card: CardInstance, aura: CardInstance, actor: str | None) -> None:
    from app.rules import layers

    plan.note(f"{card.name}: {aura.name} is sacrificed instead of the destruction", [card.id, aura.id], actor=actor)
    plan.do({"type": "move", "card_ids": [aura.id], "to": {"zone": "graveyard"}}, actor=actor)
    layers.add_effect(plan, affected=[plan.oid(card)], layer="6", source=plan.oid(aura), controller=aura.controller,
                      add_keywords=("indestructible",), duration="end_of_turn", label="indestructible (sacrificed Aura)")
