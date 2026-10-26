"""-- wave 110E -- "As this Equipment becomes attached to a creature, choose a color." (Sanctuary Blade).

701.3a: attaching moves the Equipment; the color is chosen by its controller as it becomes attached (it is no trigger, nothing can respond), and
"the last chosen color" is the most recent such choice, kept on the Equipment like an entering choice ("Chosen color"). Only the equip ability asks;
any other way to attach it leaves it where it is (attachments.attach) and the player moves it by hand.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STATIC = "attach_choice110e"
LINE = "As this Equipment becomes attached to a creature, choose a color."


def needs(plan: Plan, card_id: str) -> bool:
    card = plan.state.cards.get(card_id)
    return card is not None and card.zone.endswith(":battlefield") and any(ab.text == LINE for ab in plan.ch(card).abilities)


def ask(plan: Plan, ctx: dict[str, Any], card_id: str, host: str) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide
    from app.rules.protection_grants import COLORS

    src = plan.state.cards[card_id]
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{src.name}: choose a color", source=src,
           options=[DecisionOption(id=c, label=c) for c in COLORS], resume={"step": "attach_choice110e", "ctx": ctx, "card": card_id, "host": host})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import attachments
    from app.rules.effects import continue_effects
    from app.rules.protection_grants import COLORS

    if len(chosen) != 1 or chosen[0] not in COLORS:
        raise ActionError("Choose one of the colors")
    r = d.resume
    plan.note(f"{plan.name(d.player)} chooses {chosen[0].lower()}", actor=d.player)
    plan.do({"type": "set_choice", "card_id": r["card"], "key": "Chosen color", "value": chosen[0]}, actor=d.player)
    attachments.attach(plan, r["card"], r["host"], d.player, chosen110e=True)
    continue_effects(plan, r["ctx"])


PRIMITIVES: dict[str, Any] = {}
RESUME: dict[str, Any] = {"attach_choice110e": resume}
