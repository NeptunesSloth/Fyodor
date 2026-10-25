"""Tevesh Szat, Doom of Fools (wave 110C): +1 sacrifice-then-draw with a commander bonus, -10 all commanders to the battlefield.

903.3: a commander is a card the owner's deck names, so the command-zone selector is built by hand (the grammar refuses "commander card").
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

_PLUS = ("+1: You may sacrifice another creature or planeswalker. If you do, draw two cards, then draw another card if the sacrificed "
         "permanent was a commander.")
_MINUS = "−10: Gain control of all commanders. Put all commanders from the command zone onto the battlefield under your control."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.text == _PLUS:  # the bonus draw reads the object the payment sacrificed (as it last existed, 608.2h)
        native = scripts.define(replace(ability, text="+1: You may sacrifice another creature or planeswalker. If you do, draw two cards."), ch)
        if native is None or [e.get("do") for e in native["effects"]] != ["optional_payment", "only_if", "draw"]:
            return None
        pay, gate, draw = native["effects"]
        gate["skip"] = 3
        bonus = {"do": "only_if", "cond": {"object": f"ref:{pay['bind']}", "is": selectors.parse("commander").key()}, "skip": 1}
        native["effects"] = [pay, gate, draw, bonus, {**draw, "n": 1}]
        return native
    if ability.text == _MINUS:  # 114.4a-style: two instructions, the second moves every commander in a command zone
        native = scripts.define(replace(ability, text="−10: Gain control of all commanders. Put all creature cards from your graveyard onto the battlefield under your control."), ch)
        if native is None or [e.get("do") for e in native["effects"]] != ["gain_control", "return_card"]:
            return None
        sel = replace(selectors.parse("creature card in your graveyard"), types=(), zones=("command",), zone_owner=None, commander=True)
        native["effects"][1]["who"] = sel.key()
        return native
    return None
