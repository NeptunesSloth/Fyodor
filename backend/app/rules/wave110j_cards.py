"""-- wave 110J -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]

_FORESTS = "half the number of Forests you control"


def _aspect(d: Def) -> Def:
    """Aspect of Wolf: X (rounded down) is the power bonus, Y (rounded up) the toughness bonus; two sentences of one static (613.4c, 107.1a)."""
    from app.rules import statics

    toughness = statics.parse(f"Enchanted creature gets +0/+X, where X is {_FORESTS}, rounded up.")
    return {**d, "p": 0, "t": 0, "also": [toughness]} if toughness and "each" in d else d


# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "Enchanted creature gets +X/+Y, where X is half the number of Forests you control, rounded down, and Y is half the number of Forests you control, rounded up.":
        (f"Enchanted creature gets +X/+0, where X is {_FORESTS}, rounded down.", _aspect),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def _farmer(d: Def) -> Def:
    """Orcish Farmer: the land stays a Swamp until its own controller's next untap step (611.2a, 502.3) — the controller of the land, not of the Farmer."""
    until = [e for e in d["effects"] if e.get("do") == "until" and e.get("duration") == "next_turn"]
    return {**d, "effects": [{**e, "controller110j": True} if e in until else e for e in d["effects"]]} if len(until) == 1 else d


_BUILD["{T}: Target land becomes a Swamp until its controller's next untap step."] = (
    "{T}: Target land becomes a Swamp until your next turn.", _farmer)
