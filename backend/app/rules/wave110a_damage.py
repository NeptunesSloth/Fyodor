"""Wave 110A: Grothama, All-Devouring - "When Grothama leaves the battlefield, each player draws cards equal to the amount of damage dealt to Grothama this turn by
sources they controlled." Each player (101.4, APNAP) draws the damage their sources dealt to that object this turn (120.3, 608.2i: the turn's damage facts, the
source's controller as it dealt it). The other line is a static grant of a triggered ability naming its granter (scripts._granter_view)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

Context = dict[str, Any]
TEXT = "When ~ leaves the battlefield, each player draws cards equal to the amount of damage dealt to ~ this turn by sources they controlled."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    d = scripts.define(replace(ability, text="When ~ leaves the battlefield, you draw a card."), ch)
    return None if d is None or [e["do"] for e in d["effects"]] != ["draw"] else {**d, "effects": [{"do": "damage_draw110a"}]}


def damage_draw(plan: Any, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects, history

    facts = [f for f in history.log_for(plan).facts if f.kind == "damaged" and f.object_id == ctx.get("source_object")]
    for p in plan.apnap():
        if n := sum(f.amount for f in facts if f.source_controller == p):
            effects.PRIMITIVES["draw"](plan, ctx, {"do": "draw", "who": f"player:{p}", "n": n})
    return True


PRIMITIVES = {"damage_draw110a": damage_draw}
