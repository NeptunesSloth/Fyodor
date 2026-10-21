"""Contested Game Ball uses the native frozen attacking-player damage receipt."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ("Whenever you're dealt combat damage, the attacking player gains control of this artifact "
        "and untaps it.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text="Whenever you're dealt combat damage, untap this artifact."), ch)
    if native is None:
        return None
    return {**native, 'effects': [{'do': 'game_ball_attacker65'}]}


def take_and_untap(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import effects

    attacker = (ctx.get('event') or {}).get('attacking_player')
    if not isinstance(attacker, str) or attacker not in plan.live():
        return True
    acting = {**ctx, 'controller': attacker}
    if not effects.gain_control(plan, ctx, {'do': 'gain_control', 'who': 'self', 'to': 'player:' + attacker}):
        return False
    return effects.untap(plan, acting, {'do': 'untap', 'who': 'self'})


PRIMITIVES = {'game_ball_attacker65': take_and_untap}
