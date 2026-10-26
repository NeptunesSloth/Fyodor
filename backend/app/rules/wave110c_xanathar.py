"""-- Xanathar, Guild Kingpin (wave 110C) -- an opponent's library top, borrowed for a turn.

* 601.3 / 305.1: a stored permission lets the controller play the top card of the chosen opponent's library this turn (``Permission.library_of``).
* 401.5: "look at the top card of their library any time" shows that card to the grantee only (visibility.top_revealed).
* 609.4b: mana of any color may be spent on those spells (spend "color").
* 614.12: the target is chosen when the trigger is put on the stack; "choose target opponent" is read as "target opponent" (115.1).
"""
from __future__ import annotations

import secrets
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

_TEXT = ("At the beginning of your upkeep, choose target opponent. Until end of turn, that player can't cast spells, you may look at the top card of "
         "their library any time, you may play the top card of their library, and you may spend mana as though it were mana of any color to cast spells "
         "this way.")


def definition(ability: AbilityText, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text != _TEXT:
        return None
    native = scripts.define(replace(ability, text="At the beginning of your upkeep, target opponent can't cast spells this turn."), ch)
    if native is None:
        return None
    return {**native, "effects": [*native["effects"], {"do": "borrow_top110c"}]}


def borrow_top(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import Permission
    from app.rules import effects

    for victim in effects._players(plan, ctx, "target"):
        pid = ctx["controller"]
        plan.rules.permissions.append(Permission(
            id=secrets.token_hex(4), player=pid, play=True, cast=True, zone="library_top", library_of=victim, look_top=True, spend="color",
            until="end_of_turn", turn=plan.state.turn.number, granted_step=plan.rules.step_serial, source=ctx.get("source_object"),
            label=f"{ctx.get('name') or 'An effect'}: play the top card of {plan.name(victim)}'s library this turn"))
        plan.note(f"{plan.name(pid)} may look at and play the top card of {plan.name(victim)}'s library this turn", actor=pid)
    return True


PRIMITIVES = {"borrow_top110c": borrow_top}
