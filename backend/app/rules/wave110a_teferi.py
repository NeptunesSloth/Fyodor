"""Wave 110A: Teferi, Who Slows the Sunset.

+1: up to one target artifact, creature and land (115.1); on resolution each chosen permanent the controller controls untaps and each other one taps
(608.2c: control is read as the ability resolves), then they gain 2 life.
-7 emblem (114.1): "Untap all permanents you control during each opponent's untap step." and "You draw a card during each opponent's draw step." are
turn-based actions (502.3, 504.1) carried out in that step, simultaneously with the active player's: no trigger, no stack, no response window.
The emblem's statics are read in the command zone (permissions._all_table_statics; designations.emblem_text_ok)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

PLUS = ("+1: Choose up to one target artifact, up to one target creature, and up to one target land. Untap the chosen permanents you control. "
        "Tap the chosen permanents you don't control. You gain 2 life.")
UNTAP = "Untap all permanents you control during each opponent's untap step."
DRAW = "You draw a card during each opponent's draw step."
STATICS = {UNTAP: "untap_opp110a", DRAW: "draw_opp110a"}
NAMES = frozenset(STATICS.values())


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if (name := STATICS.get(text)) is not None:
        return {"kind": "static", "static": name, "effects": []}
    if text != PLUS:
        return None
    d = scripts.define(replace(ability, text="+1: Tap up to one target artifact, up to one target creature, and up to one target land. You gain 2 life."), ch)
    if d is None or [e["do"] for e in d["effects"]] != ["tap", "tap", "tap", "gain_life"]:
        return None
    return {**d, "effects": [{"do": "flip110a", "who": e["who"]} for e in d["effects"][:3]] + d["effects"][3:]}


def flip(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Untap the chosen permanent if its controller is the ability's controller, else tap it."""
    from app.rules import effects

    for c in effects._cards(plan, ctx, e["who"]):
        mine = plan.state.cards[c].controller == ctx["controller"]
        effects.PRIMITIVES["untap" if mine else "tap"](plan, ctx, {"do": "untap" if mine else "tap", "who": "object:" + plan.oid(c)})
    return True


def holders(plan: Any, name: str) -> list[str]:
    """The players (not the active one) whose emblems have the static: each emblem counts (several emblems act several times)."""
    from app.rules import permissions

    live = plan.live()
    return [src.controller for src, _, _d in permissions._table_statics(plan.state, plan.info, {name}) if src.controller in live and src.controller != plan.active]


def untap_step(plan: Any) -> None:
    """502.3: in the active player's untap step, the emblem holders' permanents untap too (a stunned one loses a stun counter instead, 122.1d)."""
    from app.rules import keyword_actions

    for pid in dict.fromkeys(holders(plan, "untap_opp110a")):
        cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == pid and c.tapped]
        cards = keyword_actions.untap_stunned(plan, cards, plan.active) if cards else []
        if cards:
            plan.do({"type": "tap", "card_ids": cards, "tapped": False}, actor=pid)


def extra_drawers(plan: Any) -> list[str]:
    """504.1: the players who also draw a card in this draw step (one per emblem)."""
    return holders(plan, "draw_opp110a")


PRIMITIVES = {"flip110a": flip}
