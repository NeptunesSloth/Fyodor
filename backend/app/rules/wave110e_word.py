"""-- wave 110E -- Word of Command: "Look at target opponent's hand and choose a card from it. You control that player until Word of Command finishes
resolving. The player plays that card if able. While doing so, the player can activate mana abilities only if they're from lands that player controls and
only if mana they produce is spent to activate other mana abilities of lands the player controls and/or to play that card. If the chosen card is cast as a
spell, you control the player while that spell is resolving."

CR 723.1 / 723.5: the control lasts only while an object resolves (``PlayerControl.obj``), not a turn: first Word of Command itself, then the cast spell
(pending until that spell starts to resolve: effects.begin_resolution). The controller makes every choice for the player, the cast and its payment included.
The mana restriction is ``PlayerControl.lands_only`` (casting.mana_sources and the by-hand mana activation read game.control.lands_only). The play is the
paid free cast of the chosen card (608.2g, timing waived), required (ruling 2011-01-01: you must order it if possible), by the controlled player.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_TEXT = ("Look at target opponent's hand and choose a card from it. You control that player until ~ finishes resolving. The player plays that card if able. "
         "While doing so, the player can activate mana abilities only if they're from lands that player controls and only if mana they produce is spent to activate "
         "other mana abilities of lands the player controls and/or to play that card. If the chosen card is cast as a spell, you control the player while that "
         "spell is resolving.")


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip().replace("Word of Command", "~") != _TEXT:
        return None
    return [{"do": "reveal_hand", "who": "target", "private": True},
            {"do": "choose_from_hand", "who": "you", "sel": 'sel:{"card":true,"zones":[]}', "n": 1, "label": "card", "optional": False, "as": "wc110e"},
            {"do": "control_word110e"},
            {"do": "free_cast", "zone": "that", "who": "ref:wc110e", "filter": None, "optional": False, "required": True, "paid": True, "play": True,
             "n": 1, "caster": "target110e"},
            {"do": "control_spell110e"}], "opponent", False


def caster(ctx: dict[str, Any]) -> str:
    return str(ctx["targets"][0]["id"])


def payable(plan: Plan, pid: str, card: Any, ch: Any) -> bool:
    """"Plays that card if able": a spell whose mana cost the lands (and the pool) can't pay, with no other way to cast it, isn't played (lands only: no hand mana)."""
    from app.rules import casting, paid_effect_costs

    cost = casting.spell_cost(plan.state, card, ch, 0, plan.info, player=pid)
    return casting.can_pay(plan.state, pid, cost, plan.info, purpose=casting.Purpose(spell=ch, card=card.id)) or bool(paid_effect_costs.alternatives(plan, card, ch, player=pid))


def control_word(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """723.1: you control the target until this spell finishes resolving; 723.1a: the last effect on a player wins."""
    from app.game.rules_state import PlayerControl

    who, me = caster(ctx), ctx["controller"]
    if who in plan.live() and who != me and ctx.get("stack_id"):
        r = plan.rules
        r.player_control = [c for c in r.player_control if not (c.controlled == who and (c.status == "pending" or c.obj))]
        r.player_control.append(PlayerControl(controlled=who, controller=me, status="active", obj=ctx["stack_id"], lands_only=True, label=ctx.get("name") or ""))
        plan.note(f"{plan.name(me)} controls {plan.name(who)} until {ctx.get('name') or 'it'} finishes resolving (723.1)", actor=me)
    return True


def control_spell(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The chosen card, if it was cast as a spell and is still on the stack: you control the player while that spell is resolving (pending until it is)."""
    from app.game.rules_state import PlayerControl

    who, me = caster(ctx), ctx["controller"]
    done = ctx.get("free_cast_done") or []
    cid = done[-1] if done else None
    card = plan.state.cards.get(cid or "")
    if card is not None and card.zone == "stack" and who in plan.live() and who != me and card.controller == who:
        plan.rules.player_control.append(PlayerControl(controlled=who, controller=me, status="pending", obj=cid or "", label=ctx.get("name") or ""))
    return True


def resolving(plan: Plan, stack_id: str) -> None:
    """The spell a pending window waits for starts to resolve: the control begins (it ends when the spell leaves the stack)."""
    r = plan.rules
    r.player_control = [c for c in r.player_control if not (c.obj and c.status == "pending" and c.obj != stack_id and c.obj not in plan.state.zones.get("stack", []))]
    for c in r.player_control:
        if c.obj == stack_id and c.status == "pending":
            c.status = "active"
            plan.note(f"{plan.name(c.controller)} controls {plan.name(c.controlled)} while {c.label or 'the spell'} resolves (723.1)", actor=c.controller)


PRIMITIVES = {"control_word110e": control_word, "control_spell110e": control_spell}
