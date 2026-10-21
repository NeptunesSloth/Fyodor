"""Bounded exact life-setting and exchange instructions."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

SHAMAN = "Formidable — {9}{G}{G}, {T}: Each player's life total becomes the number of creatures they control. Activate only if creatures you control have total power 8 or greater."
AXIS = "At the beginning of your upkeep, you may have two target players exchange life totals."
TOUCH = "At the beginning of your upkeep, count the number of permanents you control. Your life total becomes that number."
PSYCHIC = "If the difference between your life total and target player's life total is 5 or less, exchange life totals with that player."
OKETRA = "Your life total becomes equal to your starting life total. Lands you control don't untap during your next untap step."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = ability.text
    if text == SHAMAN:
        base = scripts.define(
            replace(
                ability,
                text=text.replace(
                    "Each player's life total becomes the number of creatures they control.",
                    "Each player gains 1 life.",
                ),
            ),
            ch,
        )
        return {**base, "effects": [{"do": "life_sets44", "mode": "biorhythm"}]} if base else None
    if text == AXIS:
        base = scripts.define(
            replace(
                ability, text="At the beginning of your upkeep, two target players exchange life totals."
            ),
            ch,
        )
        return {**base, "optional": True} if base else None
    if text == TOUCH:
        base = scripts.define(replace(ability, text="At the beginning of your upkeep, you gain 1 life."), ch)
        return {**base, "effects": [{"do": "life_dynamic45", "mode": "permanents"}]} if base else None
    if text == PSYCHIC:
        base = scripts.define(replace(ability, text="Exchange life totals with target player."), ch)
        return {**base, "effects": [{"do": "life_dynamic45", "mode": "within_five"}]} if base else None
    if text == OKETRA:
        base = scripts.define(
            replace(ability, text=text.replace("equal to your starting life total", "20")), ch
        )
        return (
            {**base, "effects": [{"do": "life_dynamic45", "mode": "starting"}, *base["effects"][1:]]}
            if base
            else None
        )
    return None


def run(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import effects

    mode = effect["mode"]
    if mode == "permanents":
        count = sum(
            c.controller == ctx["controller"] and c.zone.endswith(":battlefield") and plan.in_game(c)
            for c in plan.state.cards.values()
        )
        steps = [{"do": "set_life", "who": "you", "n": count}]
    elif mode == "starting":
        steps = [{"do": "set_life", "who": "you", "n": plan.state.settings.starting_life}]
    elif mode == "within_five":
        players = effects._players(plan, ctx, "target")
        if (
            not players
            or abs(plan.state.players[players[0]].life - plan.state.players[ctx["controller"]].life) > 5
        ):
            return True
        steps = [{"do": "exchange_life", "who": "you", "with": "target"}]
    else:
        raise ValueError("Unknown dynamic life instruction")
    ctx["effects"][ctx["next"] : ctx["next"]] = steps
    return True


PRIMITIVES = {"life_dynamic45": run}
