"""-- wave 110B -- exact Oracle wordings of single cards, read as a wording the grammar already reads (``_AS``) or built from parts of it.

Each entry matches one whole ability's Oracle text exactly (plural names and "and/or" included) and nothing else; any other wording stays
unsupported. Researched against the Comprehensive Rules of 2026-09-25.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]


def firebending(line: str) -> int | None:
    """702.189a: N of the one "firebending N" piece of a keyword line ("Trample, firebending 4, haste"), else None."""
    pieces = [p.strip() for p in re.split(r"[,;]\s*", re.sub(r"\s*\([^()]*\)", "", line).strip().rstrip("."))]
    found = [re.fullmatch(r"firebending (\d+)", p.lower()) for p in pieces if p.lower().startswith("firebending")]
    return int(found[0][1]) if len(found) == 1 and found[0] else None


# whole ability text -> the wording the grammar reads for it
_AS: dict[str, str] = {
    # Ran and Shaw: one object with a plural name (201.5); "Dragon and/or Lesson" is a card with either subtype
    "When Ran and Shaw enter, if you cast them and there are three or more Dragon and/or Lesson cards in your graveyard, create a token that's a copy "
    "of Ran and Shaw, except it's not legendary.":
        "When this creature enters, if you cast it and there are three or more Dragon or Lesson cards in your graveyard, create a token that's a copy "
        "of this creature, except it's not legendary.",
}


def _swap_value(d: Def, old: Def, new: Def) -> Def:
    """The native definition with the one condition value ``old`` read as ``new``."""
    hit = [c for c in d["conditions"] if c.get("value") == old]
    assert len(hit) == 1
    return {**d, "conditions": [{**c, "value": new} if c is hit[0] else c for c in d["conditions"]]}


def _gated(n: int) -> Callable[[Def], Def]:
    """The one kicked gate (a promised gift is a kicked spell, 702.174k) covers the ``n`` instructions after it."""
    return lambda d: {**d, "effects": [{**e, "n": n} if e["do"] == "kicked_gate" else e for e in d["effects"]]}


# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    # Perch Protection: all three instructions are conditional on the promised gift (608.2c: one sentence)
    "Create four 2/2 blue Bird creature tokens with flying. If the gift was promised, all permanents you control phase out, and until your next turn, "
    "your life total can't change and you gain protection from everything.":
        ("Create four 2/2 blue Bird creature tokens with flying. If the gift was promised, all permanents you control phase out. Until your next turn, "
         "your life total can't change. You gain protection from everything until your next turn.", _gated(3)),
    # Marvo: the clash he won (701.30d), as Entangling Trap's "if you won" reads it
    "Whenever you win a clash, draw a card. Then you may cast a spell from your hand with mana value 8 or less without paying its mana cost.":
        ("Whenever you clash, draw a card. Then you may cast a spell from your hand with mana value 8 or less without paying its mana cost.",
         lambda d: {**d, "if": {"clash_won100a": True}}),
    # Ozai: the mana a player would lose stays in the pool as red mana (614.1a, 500.4)
    "If you would lose unspent mana, that mana becomes red instead.":
        ("If you would lose unspent mana, that mana becomes colorless instead.", lambda d: {**d, "to": "R"}),
    # Ozai: unspent mana of any type, in the pool and in units with restrictions (106.4)
    "Ozai has flying and indestructible as long as you have six or more unspent mana.":
        ("Ozai has flying and indestructible as long as you have six or more cards in your hand.",
         lambda d: _swap_value(d, {"hand": "you"}, {"unspent": ""})),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = ability.text.strip()
    if (same := _AS.get(text)) is not None:
        return scripts.define(replace(ability, text=same), ch)
    if (built := _BUILD.get(text)) is not None:
        native = scripts.define(replace(ability, text=built[0]), ch)
        return None if native is None else built[1](native)
    return None


_VINCENT = ('Until end of turn, target creature you control gains "When this creature dies, return it to the battlefield tapped under its owner\'s '
            'control" and has the chosen base power and toughness.')
_TIER = re.compile(r"• (?P<label>[^—{}]+) — (?P<cost>(?:\{[^}]+\})+) — (?P<p>\d+)/(?P<t>\d+)\.")


def tiered(ch: Any, lines: list[Any]) -> Def | None:
    """Vincent's Limit Break (702.183a): the line above the tiers is the spell, each tier gives the base power and toughness it names (613.4b)."""
    from app.rules import scripts

    found = [_TIER.fullmatch(ab.text) for ab in lines[1:]]
    if len(lines) != 4 or lines[0].text != _VINCENT or None in found:
        return None
    modes = []
    for m in found:
        assert m is not None
        parts = [scripts.define(replace(lines[0], text=t), ch) for t in (
            'Until end of turn, target creature you control gains "When this creature dies, return it to the battlefield tapped under its owner\'s control."',
            f"Until end of turn, target creature you control has base power and toughness {m['p']}/{m['t']}.")]
        if None in parts or [d["target"] for d in parts if d] != [parts[0]["target"]] * 2:  # type: ignore[index]
            return None
        assert parts[0] is not None and parts[1] is not None
        modes.append({"text": f"{m['label']} — {m['cost']} — {m['p']}/{m['t']}.", "effects": [*parts[0]["effects"], *parts[1]["effects"]],
                      "target": parts[0]["target"], "cost": m["cost"]})
    return {"kind": "spell", "effects": [], "target": None, "modes": modes, "modal": {"min": 1, "max": 1, "repeat": False, "condition": None}}


PRIMITIVES: dict[str, Any] = {}
