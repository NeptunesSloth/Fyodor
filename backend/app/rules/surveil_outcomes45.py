"""Exact Starving Revenant consumes native completed surveil-kept receipts."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = "surveil_kept_draw45"
RECEIPT = "revenant45"
TEXT = "When ~ enters, surveil 2. Then for each card you put on top of your library, you draw a card and you lose 3 life."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    base = scripts.define(replace(ability, text="When ~ enters, surveil 2."), ch)
    if base is None or len(base.get("effects", [])) != 1 or base["effects"][0].get("do") != "surveil":
        return None
    return {**base, "effects": [{**base["effects"][0], "as_kept": RECEIPT}, {"do": STEP}]}


def run(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    amount = ctx.get("surveil_kept", {}).get(RECEIPT)
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        decide(
            plan,
            player=ctx["controller"],
            kind="manual_resolution",
            prompt="This older saved surveil lacks its kept-card receipt. Resolve the remaining draws and life loss by hand, then press Done.",
            options=[DecisionOption(id="done", label="Done")],
            resume={"step": "surveil_kept_legacy45", "ctx": ctx},
        )
        return False
    steps = [
        part
        for _ in range(amount)
        for part in [{"do": "draw", "who": "you", "n": 1}, {"do": "lose_life", "who": "you", "n": 3}]
    ]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *steps, *ctx["effects"][at:]]
    return True


def legacy_done(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if chosen != ["done"]:
        raise ActionError("Press Done after completing the remaining instruction")
    effects.continue_effects(plan, d.resume["ctx"])


PRIMITIVES = {STEP: run}
RESUME = {"surveil_kept_legacy45": legacy_done}
