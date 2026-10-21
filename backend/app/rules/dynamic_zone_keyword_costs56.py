"""Native granted keyword costs retain their source and actual later cast face."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.mana_cost_templates import GrantedManaCost


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == "Each nonland card in your hand without foretell has foretell. Its foretell cost is equal to its mana cost reduced by {2}.":
        return {"kind": "static", "static": "dynamic_zone_keyword56", "keyword": "foretell", "generic_reduction": 2, "effects": []}
    if text == "Whenever you foretell a card, ~ gets +2/+0 until end of turn.":
        parsed = scripts.parse_effects("~ gets +2/+0 until end of turn.")
        if parsed is None:
            return None
        return {"kind": "triggered", "trigger": "event", "cond": {"event": "foretell", "subject": "player", "player": "you"},
                "effects": parsed[0], "target": None, "optional": False}
    return None


def apply(state: Any, card: Any, ch: Any, info: Any) -> Any:
    from app.rules import permissions
    from app.rules.oracle import parse_abilities

    if "Land" in ch.types or any("foretell" in ability.keywords for ability in ch.abilities):
        return ch
    for source, _, definition in permissions._table_statics(state, info, {"dynamic_zone_keyword56"}):
        if card.owner != source.controller or card.zone != source.controller + ":hand":
            continue
        template = GrantedManaCost("foretell", state.rules.object_id(source.id), definition["generic_reduction"])
        ability = parse_abilities("Foretell")[0]
        index = max([ability.index for ability in ch.abilities], default=99) + 1
        ability = replace(ability, index=max(100, index), granted_mana_cost=template)
        return replace(ch, abilities=(*ch.abilities, ability))
    return ch


def foretell_faces(state: Any, player: str, card: Any, info: Any) -> tuple[int, ...] | None:
    receipt = state.rules.foretell_templates.get(card.id) if state.rules is not None else None
    data = info.get(card.card_id) if card.card_id else None
    if receipt is not None and receipt.object_id == state.rules.object_id(card.id) and card.zone == player + ":foretell" and card.owner == player and data and data.get("layout") == "modal_dfc":
        return tuple(range(len(data.get("faces") or [])))
    return None
