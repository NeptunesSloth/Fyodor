"""-- wave 110E -- "The next time one or more enchantment creatures you control enter this turn, each enters with two additional +1/+1 counters on it." (Storyweave).

614.1c: a one-shot replacement of the entering event; 614.12: it applies to every matching permanent of that one event (``replacements.move_together``), then it is
used up. The counters ride the ``entry_counters`` layer-6 effect the Cavern-style riders use (casting_timing_permissions.entering_counters); the effect is removed
after the first entry event that had a matching permanent, or at end of turn.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def arm(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import layers

    layers.add_effect(plan, affected=[], layer="6", source=ctx.get("source_object"), controller=ctx["controller"], duration="end_of_turn",
                      who=e["sel"], source_card=ctx.get("source_card"), entry_counters={e["kind"]: e["n"]}, entry_once110e=True, label=ctx.get("name") or "Next entry")
    return True


def spend(plan: Plan, entered: list[str]) -> None:
    """After one entry event: the armed one-shots with a matching permanent among ``entered`` are used up."""
    from app.rules import selectors

    for fx in [f for f in plan.rules.effects if f.entry_once110e]:
        for cid in entered:
            card = plan.state.cards.get(cid)
            if card is not None and card.zone.endswith(":battlefield") and fx.who and selectors.matches(
                    plan, selectors.from_key(fx.who), card, plan.ch(card), fx.controller, fx.source_card):
                plan.rules.effects = [f for f in plan.rules.effects if f.id != fx.id]
                break


PRIMITIVES: dict[str, Any] = {"next_entry_counters110e": arm}
