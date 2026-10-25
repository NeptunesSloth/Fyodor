"""-- cards (wave 110F) -- exact Oracle bodies of PARTIAL cards, read onto existing machinery. ``BUILDERS``: whole spell body -> parsed effects."""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]


def _p(text: str) -> Parsed:
    from app.rules import scripts

    got = scripts.parse_effects(text)
    if got is None:
        raise AssertionError(f"wave110f: the grammar no longer reads {text!r}")
    return copy.deepcopy(got)


def _rivals_duel() -> Parsed:
    """Rivals' Duel: two targets that share no creature types (601.2c, 205.3m) fight each other (701.14a-b: one gone, no fight)."""
    _, targets, optional = _p("Choose two target creatures that share a creature type.")
    spec = targets[0]
    spec["shares_none"] = spec.pop("shares")
    return [{"do": "fight", "who": "target:0", "twin110f": True}], targets, optional


def _dead_ringers() -> Parsed:
    """Dead Ringers: "unless either one is a color the other isn't" = destroy only when both targets have exactly the same colors (105.2)."""
    effects, targets, optional = _p("Destroy two target nonblack creatures. They can't be regenerated.")
    return [{"do": "same_colors110f", "skip": len(effects)}, *effects], targets, optional


def same_colors(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Skip the next ``skip`` effects unless the two chosen targets (both still legal, 608.2b) have the same set of colors.
    ponytail: with one target gone nothing is destroyed (the other's colors can't be compared)."""
    from app.rules import effects

    cards = effects._cards(plan, ctx, "target:0")
    if len(cards) != 2 or len({frozenset(plan.ch(plan.state.cards[c]).colors) for c in cards}) != 1:
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


BUILDERS: dict[str, Callable[[], Parsed]] = {
    "Destroy two target nonblack creatures unless either one is a color the other isn't. They can't be regenerated.": _dead_ringers,
    "Choose two target creatures that share no creature types. Those creatures fight each other.": _rivals_duel,
}
PRIMITIVES: dict[str, Any] = {"same_colors110f": same_colors}


def parse(body: str) -> Parsed | None:
    build = BUILDERS.get(body.strip())
    return build() if build is not None else None
