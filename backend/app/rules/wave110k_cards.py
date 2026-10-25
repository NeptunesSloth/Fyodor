"""-- wave 110K -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's (or spell's) Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from typing import Any

Def = dict[str, Any]

# -- Library of Lat-Nam: "An opponent chooses one —" (608.2d: the mode is chosen on resolution by the player the text names) --
_LATNAM = ["An opponent chooses one —", "• You draw three cards at the beginning of the next turn's upkeep.",
           "• You search your library for a card, put that card into your hand, then shuffle."]
_LATNAM_MODES = ["Draw three cards at the beginning of the next turn's upkeep.", "Search your library for a card, put that card into your hand, then shuffle."]


def spell(ch: Any, lines: list[Any]) -> Def | None:
    """Spell definitions of whole-spell wordings: the chooser's modes are read as the native wording of each bullet."""
    from app.rules import scripts

    if [x.text for x in lines] != _LATNAM:
        return None
    modes = [scripts.parse_effects(m) for m in _LATNAM_MODES]
    if any(m is None or m[1] is not None for m in modes):
        return None
    return {"kind": "spell", "whole110k": True, "effects": [{"do": "opponent_mode110k", "modes": [m[0] for m in modes if m is not None],
                                          "labels": ["Its controller draws three cards at the beginning of the next turn's upkeep",
                                                     "Its controller searches their library for a card"]}]}


def opponent_mode(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """An opponent picks the mode; with several opponents the controller picks which one (800.4: only players still in the game)."""
    from app.rules import effects

    opponents = [p for p in plan.apnap() if p != ctx["controller"] and p in plan.live()]
    if not opponents:
        return True
    if len(opponents) > 1:
        effects.decide(plan, player=ctx["controller"], kind="choose_one", prompt="Choose an opponent to choose the mode",
                       options=[effects.DecisionOption(id=p, label=plan.name(p)) for p in opponents],
                       resume={"step": "opponent_mode110k", "ctx": ctx, "effect": e, "opponents": opponents})
        return False
    return _ask(plan, ctx, e, opponents[0])


def _ask(plan: Any, ctx: dict[str, Any], e: dict[str, Any], chooser: str) -> bool:
    from app.rules import effects

    effects.decide(plan, player=chooser, kind="choose_one", prompt=f"{ctx.get('name') or 'Choose one'}: choose one",
                   options=[effects.DecisionOption(id=str(i), label=label) for i, label in enumerate(e["labels"])],
                   resume={"step": "opponent_mode110k", "ctx": ctx, "effect": e})
    return False


def resume_opponent_mode(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["effect"]
    if "opponents" in d.resume:
        if chosen[0] not in d.resume["opponents"]:
            raise ValueError("not an opponent")
        _ask(plan, ctx, e, chosen[0])
        return
    if chosen[0] not in {str(i) for i in range(len(e["modes"]))}:
        raise ValueError("not a mode")
    ctx["effects"][ctx["next"]:ctx["next"]] = e["modes"][int(chosen[0])]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"opponent_mode110k": opponent_mode}
RESUME = {"opponent_mode110k": resume_opponent_mode}
