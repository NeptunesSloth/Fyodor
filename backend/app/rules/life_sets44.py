"""Staged exact life-set and post-exchange token instructions."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

BIORHYTHM = "Each player's life total becomes the number of creatures they control."
PROFANE = "Two target players exchange life totals. You create an X/X colorless Horror artifact creature token, where X is the difference between those players' life totals."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text == BIORHYTHM:
        base = scripts.define(replace(ability, text="Each player gains 1 life."), ch)
        return {**base, "effects": [{"do": "life_sets44", "mode": "biorhythm"}]} if base else None
    if ability.text == PROFANE:
        base = scripts.define(replace(ability, text="Two target players exchange life totals."), ch)
        return {**base, "effects": [{"do": "life_sets44", "mode": "profane"}]} if base else None
    return None


def run(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import effects, scripts

    mode = effect["mode"]
    if mode == "biorhythm":
        counts = {
            pid: sum(
                card.controller == pid
                and card.zone.endswith(":battlefield")
                and plan.in_game(card)
                and plan.ch(card).is_creature
                for card in plan.state.cards.values()
            )
            for pid in plan.live()
        }
        steps = [{"do": "set_life", "who": "each_player", "n": 0, "values": counts}]
    elif mode == "profane":
        players = list(dict.fromkeys(effects._players(plan, ctx, "target")))
        # 608.2b: neither exchange nor the dependent token instruction can use an illegal target's life total.
        if len(players) != 2:
            return True
        steps = [
            {"do": "exchange_life", "who": "target"},
            {"do": "life_sets44", "mode": "horror", "players": players},
        ]
    elif mode == "horror":
        players = effect["players"]
        if any(pid not in plan.live() for pid in players):
            return True
        size = abs(plan.state.players[players[0]].life - plan.state.players[players[1]].life)
        native = scripts.parse_effects("Create a 1/1 colorless Horror artifact creature token.")
        assert native is not None
        token = {**native[0][0]["token"], "power": str(size), "toughness": str(size)}
        # Insert a fully built native primitive; token-order pauses never recompute X.
        steps = [{**native[0][0], "token": token}]
    else:
        raise ValueError("Unknown life-set instruction")
    ctx["effects"][ctx["next"] : ctx["next"]] = steps
    return True


PRIMITIVES = {"life_sets44": run}
