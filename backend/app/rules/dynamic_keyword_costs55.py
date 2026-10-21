"""Bind granted keyword costs to the actual selected spell, preserving announced X."""
from __future__ import annotations

from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == "Each creature spell you cast has emerge. The emerge cost is equal to its mana cost.":
        return {"kind": "static", "static": "alt_cost", "table": True, "dynamic_keyword": "emerge", "minimum_mana_value": None, "effects": []}
    if text == "Each creature spell you cast with mana value 4 or greater has blitz. The blitz cost is equal to its mana cost.":
        return {"kind": "static", "static": "alt_cost", "table": True, "dynamic_keyword": "blitz", "minimum_mana_value": 4, "effects": []}
    if text == "When you cast this spell, you may exile your hand. If you do, draw three cards.":
        return {"kind": "triggered", "trigger": "cast_self", "optional": True, "target": None,
                "effects": [{"do": "discard", "who": "you", "n": 0, "all": True, "to": "exile"},
                            {"do": "draw", "who": "you", "n": 3}]}
    if text == "Blitz costs you pay cost {1} less for each time you've cast your commander from the command zone this game.":
        return {"kind": "static", "static": "blitz_cost_reduction55", "effects": []}
    return None


def blitz_discount(state: Any, player: str, info: Any) -> int:
    from app.rules import permissions

    count = sum(state.players[player].commander_casts.values())
    return count * sum(1 for source, _, _ in permissions._table_statics(state, info, {"blitz_cost_reduction55"})
                       if source.controller == player)


def offer(source: Any, index: int, definition: dict[str, Any], ch: Any) -> Any:
    from app.rules import alt_costs
    from app.rules import mana as M

    if "Creature" not in ch.types or not ch.mana_cost:
        return None
    cost = M.parse_cost(ch.mana_cost)
    if cost.unsupported:
        return None
    minimum = definition["minimum_mana_value"]
    if minimum is not None and not cost.x and ch.mana_value < minimum:
        return None
    keyword = definition["dynamic_keyword"]
    text = "pay " + cost.text() + (" and sacrifice a creature" if keyword == "emerge" else "")
    alternative = alt_costs.parse_cost(text, x_ok=True)
    if alternative is None:
        return None
    return alt_costs.Offer(f"{source.id}:{index}", f"{source.name}: {keyword} {cost.text()}", alternative,
                          tag=keyword, minimum_mana_value=minimum)
