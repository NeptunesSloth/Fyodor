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


def _taunt() -> Parsed:
    """Taunt: for the target player's next turn (611.2a, restrict ``their_turn``), their creatures, those arriving later too (611.2c), attack the
    controller if able (508.1d; ``attack_player``, as encore's tokens)."""
    effects, targets, optional = _p("Creatures target player controls attack this turn if able.")
    assert effects[0]["rules"] == ["must_attack"]
    return [{**effects[0], "rules": ["attack_player:@you"], "duration": "their_turn"}], targets, optional


BUILDERS: dict[str, Callable[[], Parsed]] = {
    "During target player's next turn, creatures that player controls attack you if able.": _taunt,
    "Destroy two target nonblack creatures unless either one is a color the other isn't. They can't be regenerated.": _dead_ringers,
    "Choose two target creatures that share no creature types. Those creatures fight each other.": _rivals_duel,
}
# Sentences the grammar reads in other words (608.2c). 509.1g: while a combat phase is going (the only time the "dies during combat" trigger fires),
# "the creatures it blocked this combat" are the creatures blocked by it (block_events reads them off its last known information).
REWRITES = {
    # 611.2 / 122.1: control change then the counter on the same (still targeted) creature, as two sentences.
    "Gain control of target nonartifact, nonblack creature that attacked you this turn and put a -1/-0 counter on it.":
        "Gain control of target nonartifact, nonblack creature that attacked you this turn, then put a -1/-0 counter on it.",
    "it deals 6 damage to each creature it blocked this combat.": "~ deals 6 damage to each creature blocked by it.",
}
PRIMITIVES: dict[str, Any] = {"same_colors110f": same_colors}


def parse(body: str) -> Parsed | None:
    from app.rules import scripts

    build = BUILDERS.get(body.strip())
    if build is not None:
        return build()
    return scripts.parse_effects(REWRITES[body.strip()]) if body.strip() in REWRITES else None
