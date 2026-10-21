"""Exact table modifiers for selected source, zone and activation-kind predicates."""

from __future__ import annotations

from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import conditions, cost_changes, scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    base: dict[str, Any] = {
        "kind": "static",
        "static": "ability_cost_modifier",
        "delta": -2,
        "filter": None,
        "who": "any",
        "floor": False,
        "effects": [],
    }
    if text == (
        "Enchanted artifact's activated abilities cost {2} less to activate. "
        "This effect can't reduce the mana in that cost to less than one mana."
    ):
        return {**base, "attached_host": True, "floor": True}
    if text == "Activated abilities of creature cards in your graveyard cost {1} less to activate.":
        return {
            **base,
            "delta": -1,
            "filter": selectors.Selector(
                types=("Creature",), card=True, zones=("graveyard",), zone_owner="you"
            ).key(),
        }
    if text == (
        "As long as you control your commander, activated abilities of cards in your graveyard cost {2} less "
        "to activate. This effect can't reduce the mana in that ability's activation cost to less than one mana."
    ):
        condition = conditions.parse("you control your commander")
        assert condition is not None
        return {
            **base,
            "filter": selectors.Selector(card=True, zones=("graveyard",), zone_owner="you").key(),
            "floor": True,
            "condition": condition,
        }
    if text == "Loyalty abilities of planeswalkers your opponents control cost {1} more to activate.":
        return {
            **base,
            "delta": 1,
            "filter": selectors.Selector(types=("Planeswalker",), controller="opponent").key(),
            "loyalty_only": True,
        }
    if text == "Boast abilities you activate cost {1} less to activate for each Dragon you control.":
        value = cost_changes._value("Dragons you control")
        assert value is not None
        return {**base, "delta": 0, "who": "you", "value": value, "sign": -1, "boast_only": True}
    return None
