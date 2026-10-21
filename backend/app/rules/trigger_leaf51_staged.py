"""Staged exact leaf continuations over native play/cast history and draw effects."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

JOKUL = "Whenever you play an Island, you may untap this creature."
DJINN = "When this creature enters, each other player may draw up to three cards."
DRUID = (
    "Whenever an opponent casts an instant spell other than the first instant spell that player casts each turn, "
    "this creature deals 4 damage to that player."
)


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != "triggered" or ability.text not in (JOKUL, DJINN, DRUID):
        return None
    from app.rules import scripts, selectors

    bases = {
        JOKUL: "Whenever you play a land, you may untap this creature.",
        DJINN: "When this creature enters, each opponent draws three cards.",
        DRUID: "Whenever an opponent casts an instant spell, this creature deals 4 damage to that player.",
    }
    native = scripts.define(replace(ability, text=bases[ability.text]), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    if ability.text == JOKUL:
        out["cond"]["obj"] = selectors.Selector(types=("Land",), subtypes=("Island",)).key()
    elif ability.text == DJINN:
        out["effects"] = [{"do": "trigger_leaf51_djinn_draws"}]
    else:
        # CR601.2i: ordinal is tied to this exact original cast event and its
        # caster. Later casts, countering and source departure cannot change it.
        out["if"] = {
            "not": {
                "as": "event",
                "cond": {
                    "history": "cast_nth",
                    "object": "event",
                    "who": "you",
                    "sel": selectors.Selector(types=("Instant",), zones=("stack",)).key(),
                    "n": 1,
                },
            }
        }
    return out


def djinn_draws(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    state = ctx.setdefault(
        "trigger_leaf51_djinn",
        {"players": [p for p in plan.apnap() if p != ctx["controller"]], "counts": {}, "at": 0},
    )
    while state["at"] < len(state["players"]):
        player = state["players"][state["at"]]
        if player not in plan.live():
            state["at"] += 1
            continue
        from app.rules import prohibitions

        cap = prohibitions.draw_left(plan, player)
        maximum = min(3, cap[0]) if cap is not None else 3
        decide(
            plan,
            player=player,
            kind="choose_one",
            prompt="Indentured Djinn: draw how many cards?",
            options=[DecisionOption(id=str(n), label=f"Draw {n}") for n in range(maximum + 1)],
            resume={
                "step": "trigger_leaf51_djinn_count",
                "ctx": ctx,
                "player": player,
                "rest": state["players"][state["at"] + 1 :],
                "picked": dict(state["counts"]),
            },
        )
        return False
    # CR101.4: all numeric choices precede actions. CR121.2c: each player
    # performs their complete set of draws in APNAP order through native draw.
    from app.rules import coin_recipes

    coin_recipes.insert(
        ctx,
        [
            {"do": "draw", "who": f"player:{p}", "n": state["counts"].get(p, 0)}
            for p in state["players"]
            if p in plan.live()
        ],
    )
    return True


def resume_djinn(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = decision.resume["ctx"]
    state = ctx["trigger_leaf51_djinn"]
    # Native per-player leave continuation supplies an empty answer; the departed
    # player makes no choice, and the remaining original recipients still act.
    if chosen and decision.resume["player"] in plan.live():
        state["counts"][decision.resume["player"]] = int(chosen[0])
    state["at"] += 1
    if djinn_draws(plan, ctx, {}):
        effects.continue_effects(plan, ctx)
