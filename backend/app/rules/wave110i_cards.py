"""-- wave 110I -- exact Oracle wordings of single cards, read as a wording the grammar already reads (``_AS``) or built from parts of it.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
Researched against the Comprehensive Rules of 2026-09-25.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
Def = dict[str, Any]


def _won_last(d: Def) -> Def:
    """701.30d: the last instruction (the token's haste) happens only if you won the clash the trigger is about."""
    *head, last = d["effects"]
    return {**d, "effects": [*head, {"do": "only_if", "cond": {"clash_won100a": True}, "skip": 1}, last]}


# whole ability text -> the wording the grammar reads for it
_AS: dict[str, str] = {
    # Corrosion: "Artifacts destroyed this way" are the ones the destroy-each instruction destroyed ("They", 701.8c: can't be regenerated)
    "At the beginning of your upkeep, put a rust counter on each artifact target opponent controls. Then destroy each artifact with mana value less than "
    "or equal to the number of rust counters on it. Artifacts destroyed this way can't be regenerated.":
        "At the beginning of your upkeep, put a rust counter on each artifact target opponent controls. Then destroy each artifact with mana value less "
    "than or equal to the number of rust counters on it. They can't be regenerated.",
}


def _until_leaves(d: Def) -> Def:
    """The Moment: "It phases out until ~ leaves the battlefield" (610.3, 702.26a): the Oubliette lifetime packet, without its tap."""
    return {**d, "effects": [{"do": "phase_until_target110c", "untapped110i": True} if x.get("do") == "phase_out" else x for x in d["effects"]]}


def _lose_types(d: Def) -> Def:
    """Curse of Conformity: "lose all creature types" sets the creature types to none (205.1a, 613.1d layer 4), beside the layer 7b base P/T."""
    return {**d, "layered": True, "layer4": {"set_creature_types": []}}


# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "Nonlegendary creatures enchanted player controls have base power and toughness 3/3 and lose all creature types.":
        ("Nonlegendary creatures enchanted player controls have base power and toughness 3/3.", _lose_types),
    "{2}, {T}: Untap target creature you control. It phases out until The Moment leaves the battlefield.":
        ("{2}, {T}: Untap target creature you control. It phases out.", _until_leaves),
    "Whenever you clash, you may pay {1}. If you do, create a 3/1 red Elemental Shaman creature token. If you won, that token gains haste until end of turn.":
        ("Whenever you clash, you may pay {1}. If you do, create a 3/1 red Elemental Shaman creature token. That token gains haste until end of turn.", _won_last),
}


# a spell / mode body -> the wording the grammar reads for it
REWRITES: dict[str, str] = {}

# Survivor's Med Kit (RadAway): "loses all rad counters" is removing every rad counter the player has (122.1i, 728). The grammar's
# "Remove all rad counters from target player" only reads permanents' counters, so its first instruction is swapped for ``lose_rad110i``.
_RADAWAY = "Target player loses all rad counters. Sacrifice ~."


def parse(body: str) -> Any:
    from app.rules import scripts

    if body.strip() == _RADAWAY:
        parsed = scripts.parse_effects("Target player gets 1 rad counters. Sacrifice ~.")
        assert parsed is not None
        effects, target, optional = parsed
        return [{"do": "lose_rad110i", "who": "target"}, *effects[1:]], target, optional
    return scripts.parse_effects(same) if (same := REWRITES.get(body.strip())) is not None else None


def lose_rad(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    for pid in effects._players(plan, ctx, e["who"]):
        if (have := plan.state.players[pid].resources.get("rad", 0)) > 0:
            plan.do({"type": "resource", "player": pid, "key": "rad", "delta": -have}, actor=ctx["controller"])
    return True


PRIMITIVES = {"lose_rad110i": lose_rad}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = ability.text.strip()
    if (same := _AS.get(text)) is not None:
        return scripts.define(replace(ability, text=same), ch)
    built = _BUILD.get(text)
    if built is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)
