"""Exact turn-scoped phase skips, with native targeting and upkeep trigger packets."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

FATES = "At the beginning of each opponent's upkeep, that player chooses draw step, main phase, or combat phase. The player skips each instance of the chosen step or phase this turn."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text in (
        "Target opponent skips all combat phases of their next turn.",
        "Target player skips all combat phases of their next turn.",
    ):
        native = scripts.define(
            replace(
                ability, text=text.replace("all combat phases of their next turn", "their next combat phase")
            ),
            ch,
        )
        return (
            {
                **native,
                "effects": [
                    {
                        "do": "skip_next",
                        "who": "target",
                        "what": "combat",
                        "next_turn88": True,
                        "repeat88": True,
                    }
                ],
            }
            if native
            else None
        )
    if text == "Target player skips their next combat phase this turn.":
        native = scripts.define(replace(ability, text="Target player skips their next combat phase."), ch)
        return (
            {**native, "effects": [{"do": "skip_next", "who": "target", "what": "combat", "this_turn": True}]}
            if native
            else None
        )
    if text == FATES:
        native = scripts.define(
            replace(ability, text="At the beginning of each opponent's upkeep, that player draws a card."), ch
        )
        return {**native, "effects": [{"do": "phase_choice88"}]} if native else None
    return None


def choose(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    players = effects._players(plan, ctx, "event_player")
    if not players:
        return True
    decide(
        plan,
        player=players[0],
        kind="choose_one",
        prompt=f"{ctx.get('name') or 'Effect'}: choose a step or phase to skip",
        options=[
            DecisionOption(id=key, label=label)
            for key, label in [("draw", "Draw step"), ("main", "Main phase"), ("combat", "Combat phase")]
        ],
        resume={"step": "phase_choice88", "ctx": ctx},
    )
    return False


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects, skips

    if len(chosen) != 1 or chosen[0] not in ("draw", "main", "combat"):
        raise ActionError("Choose one of the offered steps or phases")
    ctx = d.resume["ctx"]
    skips.skip_next(
        plan, ctx, {"who": "event_player", "what": chosen[0], "this_turn": True, "repeat88": True}
    )
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"phase_choice88": choose}
RESUME = {"phase_choice88": resume}
