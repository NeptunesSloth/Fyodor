"""-- core (wave 110C) -- exact Oracle wordings (whole ability or spell body) built from what the grammar already reads plus a few primitives.

Each entry matches one whole text exactly; any other wording stays unsupported. ``~`` stands for the card's name, as in multi100n.
"""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

Parsed = tuple[list[dict[str, Any]], Any, bool]
Context = dict[str, Any]


def read(text: str) -> Parsed:
    """What scripts.parse_effects reads for a native wording (the build fails loudly if the grammar stops reading it)."""
    from app.rules import scripts

    got = scripts.parse_effects(text)
    if got is None:
        raise AssertionError(f"wave110c: the grammar no longer reads {text!r}")
    return copy.deepcopy(got)


def _catastrophe() -> Parsed:
    """Catastrophe: the choice of lands or creatures is made as it resolves (608.2d); only the creatures' destruction can't be regenerated (701.19c)."""
    lands = read("Destroy all lands.")[0]
    creatures = read("Destroy all creatures. They can't be regenerated.")[0]
    return [{"do": "choose_branch110c", "who": "you", "options": [{"label": "Destroy all lands", "effects": lands},
                                                                  {"label": "Destroy all creatures", "effects": creatures}]}], None, False


def _paid(cost: str) -> dict[str, Any]:
    """"The {2}{U} cost was paid": the spell's one alternative cost (118.9a), read from its payment record (conditions._cast_how)."""
    from app.rules import conditions

    got = conditions.parse(f"the {cost} cost was paid", objects=True)
    assert got is not None
    return got


def _instead(cond: dict[str, Any], base: list[dict[str, Any]], alt: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """"If C, A. If not, B.": C judged once as the spell resolves (608.2c), then exactly one of the two (base runs when C fails)."""
    return [{"do": "only_if", "cond": {"not": cond}, "skip": len(base), "bind": "cond0"}, *base,
            {"do": "only_if", "cond": {"flag": "cond0", "negate": True}, "skip": len(alt)}, *alt]


def _ingenious_mastery() -> Parsed:
    """Ingenious Mastery: paid, you draw three cards, then an opponent (one you choose as it resolves: its 2021-04-16 ruling) creates two Treasure
    tokens and scries 2; else you draw X cards. A copy resolves as if the cost was paid (its ruling; the copy's record is the original's)."""
    opponent = read("An opponent draws a card.")[0][0]
    treasure = read("Each opponent creates two Treasure tokens.")[0][0]
    scry = read("Scry 2.")[0][0]
    paid = [*read("Draw three cards.")[0], opponent, {**treasure, "who": "ref:copp"}, {**scry, "who": "ref:copp"}]
    return _instead(_paid("{2}{U}"), read("Draw X cards.")[0], paid), None, False


def _devastating_mastery() -> Parsed:
    """Devastating Mastery: paid, an opponent you choose as it resolves chooses up to two nonland permanents they control and returns them to
    their owner's hand (their choice: 701.? no — the player returns them; a "returns" is theirs to make, not a bounce of yours)."""
    opponent = read("An opponent draws a card.")[0][0]
    chosen = read("Target opponent chooses up to two creatures they control. Return those creatures to their owner's hand.")[0]
    pick = {**chosen[0], "who": "ref:copp", "sel": read("Target opponent chooses up to two nonland permanents they control.")[0][0]["sel"],
            "label": "nonland permanents"}
    return [{"do": "only_if", "cond": _paid("{2}{W}{W}"), "skip": 3}, opponent, pick, chosen[1]], None, False


BUILDERS: dict[str, Callable[[], Parsed]] = {
    "If the {2}{U} cost was paid, you draw three cards, then an opponent creates two Treasure tokens and they scry 2. If that cost wasn't paid, "
    "you draw X cards.": _ingenious_mastery,
    "If the {2}{W}{W} cost was paid, an opponent chooses up to two nonland permanents they control and returns them to their owner's hand.":
        _devastating_mastery,
    "Destroy all lands or all creatures. Creatures destroyed this way can't be regenerated.": _catastrophe,
}


def parse(body: str) -> Parsed | None:
    build = BUILDERS.get(body.strip())
    return build() if build is not None else None


def definition(ability: AbilityText, ch: Any) -> dict[str, Any] | None:
    return None


# -- carrying it out -----------------------------------------------------------------------------------
def choose_branch(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """``who`` (a player) chooses one of ``options`` ({"label", "effects"}); its effects run in place of this instruction (608.2d)."""
    from app.game.rules_state import DecisionOption
    from app.rules.effects import _players
    from app.rules.plan import decide

    chooser = (_players(plan, ctx, e["who"]) or [ctx["controller"]])[0]
    decide(plan, player=chooser, kind="choose_one", prompt=f"{ctx.get('name') or 'Effect'}: choose one",
           options=[DecisionOption(id=str(i), label=o["label"]) for i, o in enumerate(e["options"])],
           resume={"step": "choose_branch110c", "ctx": ctx, "e": e}, source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume_branch(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one of the offered options")
    option = e["options"][int(chosen[0])]
    plan.note(f"{plan.name(d.player)} chooses {option['label'].lower()}", actor=d.player)
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *copy.deepcopy(option["effects"]), *ctx["effects"][at:]]
    continue_effects(plan, ctx)


PRIMITIVES = {"choose_branch110c": choose_branch}
RESUME = {"choose_branch110c": resume_branch}
