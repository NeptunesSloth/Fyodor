"""Entering choice made by an opponent (wave 110E): "As ~ enters, an opponent chooses a creature type." (Callous Oppressor).

614.12a: the choice is made as the permanent enters. The text says "an opponent", so the controller picks which one
(only asked with 2+ opponents, 800.4: dead players are gone); that opponent then answers."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import Plan

WHO = "chooser110e"


def decider(plan: Plan, controller: str, answers: dict[str, str], out: dict[str, Any]) -> str | None:
    """The opponent who answers, or None while the controller still has to pick one (``out["choice"]`` is then that question)."""
    opponents = [p for p in plan.live() if p != controller]
    if len(opponents) == 1:
        return opponents[0]
    if answers.get(WHO) in opponents:
        return answers[WHO]
    out.setdefault("choice", {"what": WHO})
    return None


def prompt(plan: Plan, card: Any, controller: str) -> tuple[str, list[DecisionOption]]:
    from app.game.rules_state import DecisionOption

    return f"{card.name}: as it enters, choose the opponent who chooses", [DecisionOption(id=p, label=plan.name(p)) for p in plan.live() if p != controller]
