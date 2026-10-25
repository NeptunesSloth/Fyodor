"""-- wave 110N -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]

_NATIVE_HEA = ("At the beginning of your upkeep, if there are five colors among permanents you control and your life total is greater than or "
               "equal to your starting life total, you win the game.")
_SIX_TYPES: Def = {"value": {"union_types110n": "you"}, "op": ">=", "n": 6}


def _hea(d: Def) -> Def:
    """Happily Ever After: the middle clause joins the native condition, in the trigger's intervening "if" (603.4) and as it resolves."""
    both = {"all": [*d["if"]["all"][:1], _SIX_TYPES, *d["if"]["all"][1:]]}
    return {**d, "if": both, "effects": [{**e, "cond": both} if e.get("do") == "only_if" else e for e in d["effects"]]}


# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "At the beginning of your upkeep, if there are five colors among permanents you control, there are six or more card types among permanents you "
    "control and/or cards in your graveyard, and your life total is greater than or equal to your starting life total, you win the game.":
        (_NATIVE_HEA, _hea),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def union_types(plan: Any, ctx: Any, v: Def) -> int:
    """205.2a: the card types shared out among the player's permanents and the cards in their graveyard (a card type, not a subtype)."""
    from app.rules.values import CARD_TYPES

    me = ctx["controller"]
    found: set[str] = set()
    for c in plan.state.cards.values():
        if (c.zone == f"{me}:battlefield" and plan.in_game(c)) or c.zone == f"{me}:graveyard":
            found |= {"Kindred" if t == "Tribal" else t for t in plan.ch(c).types if t in CARD_TYPES}
    return len(found)


PRIMITIVES: dict[str, Any] = {}
RESUME: dict[str, Any] = {}
