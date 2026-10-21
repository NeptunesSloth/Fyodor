"""Kicker changes native effect bundles and the actual spell's stack keyword."""
from __future__ import annotations

from dataclasses import replace
from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    if body == "Target creature can't be the target of spells or abilities your opponents control this turn. If this spell was kicked, that creature gets +4/+4 until end of turn.":
        pump = scripts.parse_effects("Target creature gets +4/+4 until end of turn.")
        if pump is None:
            return None
        return ([{"do": "restrict", "who": "target", "rules": ["untargetable_by_opponents_of:@you"]},
                 {"do": "kicked_gate", "kicked": True, "n": len(pump[0])}, *pump[0]], pump[1], False)
    if body == "~ deals 3 damage to any target. If this spell was kicked, instead it deals 10 damage to that permanent or player and the damage can't be prevented.":
        base = scripts.parse_effects("~ deals 3 damage to any target.")
        if base is None:
            return None
        return ([{"do": "kicked_gate", "kicked": False, "n": 1}, *base[0],
                 {"do": "kicked_gate", "kicked": True, "n": 1},
                 {**base[0][0], "n": 10, "unpreventable": True}], base[1], False)
    if body == "~ deals 2 damage to any target. If this spell was kicked, that creature can't be regenerated this turn and if it would die this turn, exile it instead.":
        base = scripts.parse_effects("~ deals 2 damage to any target. If it's a creature, it can't be regenerated this turn, and if it would die this turn, exile it instead.")
        if base is None:
            return None
        return ([base[0][0], {"do": "kicked_gate", "kicked": True, "n": len(base[0]) - 1}, *base[0][1:]], base[1], False)
    return None


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text == "If this spell was kicked, it has split second.":
        return {"kind": "static", "static": "own_spell_kicked_keyword59", "keyword": "split second", "effects": []}
    return None


def apply_stack(state: Any, card: Any, ch: Any, info: Any) -> Any:
    from app.rules.oracle import parse_abilities

    entry = state.rules.stack.get(card.id) if state.rules is not None else None
    if entry is None or entry.kind != "spell" or not entry.kicked:
        return ch
    for ability in ch.abilities:
        native = definition(ability, ch)
        if native is not None and native["keyword"] not in ch.keywords:
            granted = parse_abilities(native["keyword"].capitalize())[0]
            return replace(ch, abilities=(*ch.abilities, replace(granted, index=max((a.index for a in ch.abilities), default=99) + 1)))
    return ch
