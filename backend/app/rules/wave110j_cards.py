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


def _cudgels(d: Def) -> Def:
    """Bronze Cudgels: X is the number of times the ability has resolved this turn, this resolution included (history.counting_resolutions)."""
    pumps = [e for e in d["effects"] if e.get("do") == "pump"]
    return {**d, "effects": [{**e, "p": {"ref_amount": "resolution"}} if e in pumps else e for e in d["effects"]]} if len(pumps) == 1 else d


_BUILD["{2}: Until end of turn, equipped creature gets +X/+0, where X is the number of times this ability has resolved this turn."] = (
    "{2}: Until end of turn, equipped creature gets +1/+0.", _cudgels)


def _all_attack(d: Def) -> Def:
    """Mob Mentality: the trigger waits for every non-Wall creature its controller has to be attacking (triggers.py all110j)."""
    return {**d, "cond": {**d["cond"], "all110j": True}} if d.get("cond", {}).get("event") == "you_attack" else d


_BUILD["Whenever all non-Wall creatures you control attack, enchanted creature gets +X/+0 until end of turn, where X is the number of attacking creatures."] = (
    "Whenever you attack with one or more non-Wall creatures, enchanted creature gets +X/+0 until end of turn, where X is the number of attacking creatures.",
    _all_attack)


_SPORES = ('Whenever this creature blocks a creature, put four fungus counters on that creature. The creature gains "This creature doesn\'t untap during your '
           'untap step if it has a fungus counter on it" and "At the beginning of your upkeep, remove a fungus counter from this creature."')
# two grants of one clause, read as two sentences (both last for good, 611.2a)
_BUILD[_SPORES] = (
    'Whenever this creature blocks a creature, put four fungus counters on that creature. That creature gains "This creature doesn\'t untap during your '
    'untap step if it has a fungus counter on it." That creature gains "At the beginning of your upkeep, remove a fungus counter from this creature."',
    lambda d: d)
