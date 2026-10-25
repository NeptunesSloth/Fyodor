"""-- wave 110O -- exact Oracle wordings of single cards, read as native instructions or built from parts of them.

Each entry matches one whole ability's (or spell body's) Oracle text exactly and nothing else; any other wording stays unsupported.
Researched against the Comprehensive Rules of 2026-09-25.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

# spell body (exact) -> the native wording
REWRITES: dict[str, str] = {}


_REMEMBRANCE = "Shuffle Serene Remembrance and up to three target cards from a single graveyard into their owners' libraries."


_THRALL = ("Gain control of target creature until end of turn. If you control a Villain with greater mana value than that creature, gain control of that "
           "creature until the end of your next turn instead. Untap that creature. It gains haste until end of turn.")


def parse(body: str) -> Any:
    from app.rules import scripts

    if body.strip() == _THRALL:  # 608.2c: the "instead" duration replaces the first one, so exactly one control effect is made
        short = scripts.parse_effects("Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn.")
        long = scripts.parse_effects("Gain control of target creature until the end of your next turn.")
        assert short and long
        (control, *rest), (until, long_control) = short[0], long[0]
        bigger = {"w110o": "villain_bigger"}
        return [{"do": "only_if", "cond": bigger, "skip": 2}, until, long_control, {"do": "only_if", "cond": {"not": bigger}, "skip": 1}, control, *rest], short[1], False

    if body.strip() == _REMEMBRANCE.replace("Serene Remembrance", "~"):  # 701.24a: the spell and the cards are shuffled in, each owner's library shuffled
        own = scripts.parse_effects("Shuffle ~ into its owner's library.")
        cards = scripts.parse_effects("Shuffle up to three target cards from a single graveyard into their owner's library.")
        assert own and cards
        return [*own[0], *cards[0]], cards[1], False
    return scripts.parse_effects(same) if (same := REWRITES.get(body.strip())) is not None else None


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    del text
    return None


def holds(plan: Plan, ctx: Context, cond: dict[str, Any]) -> bool:
    """Evil's Thrall: you control a Villain whose mana value is greater than the target creature's (the target as it is now, 608.2b)."""
    from app.rules import effects, stack_interaction

    assert cond["w110o"] == "villain_bigger"
    target = [stack_interaction.mana_value(plan.state.cards[c], plan.ch(plan.state.cards[c])) for c in effects._cards(plan, ctx, "target")]
    return bool(target) and any(
        "Villain" in plan.ch(c).subtypes and stack_interaction.mana_value(c, plan.ch(c)) > target[0]
        for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == ctx["controller"])


PRIMITIVES: dict[str, Any] = {}
RESUME: dict[str, Any] = {}
