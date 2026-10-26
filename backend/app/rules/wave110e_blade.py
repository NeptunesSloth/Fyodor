"""-- wave 110E -- "As this Equipment becomes attached to a creature, choose a color." (Sanctuary Blade).

701.3a: attaching moves the Equipment; the color is chosen by its controller as it becomes attached (it is no trigger, nothing can respond), and
"the last chosen color" is the most recent such choice, kept on the Equipment like an entering choice ("Chosen color"). Every way to attach goes
through attachments.attach (one decision slot, possibly busy): it queues the Equipment, engine.settle asks before anyone gets priority.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STATIC = "attach_choice110e"
LINE = "As this Equipment becomes attached to a creature, choose a color."


def queue(plan: Plan, card_id: str) -> None:
    card = plan.state.cards.get(card_id)
    if card is not None and card.zone.endswith(":battlefield") and any(ab.text == LINE for ab in plan.ch(card).abilities) and card_id not in plan.rules.attach_asks110e:
        plan.rules.attach_asks110e.append(card_id)


def ask(plan: Plan, queued: list[str]) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide
    from app.rules.protection_grants import COLORS

    src = plan.state.cards.get(queued[0])
    if src is None or not src.zone.endswith(":battlefield") or src.attached_to is None:
        queued.pop(0)  # it left or came unattached before it was asked: nothing to choose
        return ask(plan, queued) if queued else None
    decide(plan, player=src.controller, kind="choose_one", prompt=f"{src.name}: choose a color", source=src,
           options=[DecisionOption(id=c, label=c) for c in COLORS], resume={"step": "attach_choice110e", "card": src.id})


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules.protection_grants import COLORS

    if len(chosen) != 1 or chosen[0] not in COLORS:
        raise ActionError("Choose one of the colors")
    card = d.resume["card"]
    if card in plan.rules.attach_asks110e:
        plan.rules.attach_asks110e.remove(card)
    plan.note(f"{plan.name(d.player)} chooses {chosen[0].lower()}", actor=d.player)
    plan.do({"type": "set_choice", "card_id": card, "key": "Chosen color", "value": chosen[0]}, actor=d.player)


PRIMITIVES: dict[str, Any] = {}
RESUME: dict[str, Any] = {"attach_choice110e": resume}
