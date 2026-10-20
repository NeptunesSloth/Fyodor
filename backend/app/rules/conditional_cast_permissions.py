"""Conditional self permissions compiled to native casting and condition paths."""
from __future__ import annotations

import re
from typing import Any


def definition(text: str, kind: str) -> dict[str, Any] | None:
    if "you may cast" not in text.lower():
        return None
    from app.rules import conditions, costs

    t = re.sub(r"\bthis card\b", "~", text.strip().rstrip("."), flags=re.IGNORECASE)
    base: dict[str, Any] = {"kind": "static", "static": "permission", "zone": "graveyard",
                            "once": False, "flash": False, "self": True, "play": False,
                            "cast": True, "filter": None, "effects": []}
    if kind == "triggered" and t == (
            "At the beginning of your end step, if you gained life this turn, "
            "you may cast ~ from your graveyard"):
        return {"kind": "triggered", "trigger": "end_step_you", "target": None,
                "optional": False, "if": conditions.parse("you gained life this turn"),
                "effects": [{"do": "free_cast", "zone": "that", "who": "self_gy",
                             "filter": None, "optional": True, "mv": None, "n": 1, "paid": True}]}
    if kind not in ("static", "spell"):
        return None
    if t.lower() == "max speed — you may cast ~ from your graveyard":
        return {**base, "while": conditions.parse("you have max speed")}
    if t.lower() == (
            "you may cast ~ from your graveyard by exiling four instant and/or sorcery cards "
            "from your graveyard in addition to paying its other costs"):
        extra = "exile four instant or sorcery cards from your graveyard"
        assert costs.parse_additional_cost(extra) is not None
        return {**base, "extra": extra}
    m = re.fullmatch(
        r"you may cast ~ from your graveyard if (?P<condition>a non-Zombie creature died this turn)"
        r"\. If you do, ~ enters with a \+1/\+1 counter on it", t, re.IGNORECASE)
    if m is not None:
        cond = conditions.parse(m["condition"])
        return {**base, "while": cond, "enters": {"counters": {"+1/+1": 1}}} if cond is not None else None
    if t.lower() == (
            "if a creature is attacking you and you control a Forest and a Plains, "
            "you may cast ~ without paying its mana cost and as though it had flash").lower():
        return {**base, "zone": "hand", "free": True, "flash": True,
                "while": conditions.parse("a creature is attacking you and you control a Forest and a Plains")}
    return None
