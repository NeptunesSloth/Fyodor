"""Wave 110A: "Enchanted creature is a copy of the chosen creature." (Metamorphic Alteration; the choice is made as the Aura enters, wave110a_pick).

Scryfall rulings 2018-07-13 (Metamorphic Alteration): the copied values are determined as the effect first begins to apply; later changes to the chosen creature, or it leaving, do not affect the enchanted creature. So it is a layer-1 copy effect (613.2a) made when the Aura
becomes attached (303.4f for an Aura entering attached) with the chosen creature's values as they are then. It lasts while that Aura stays attached to that creature
(611.2b, delayed.expire "while_attached110l"), as Blade of Shared Souls' copy does. If the chosen creature is no longer on the battlefield when the effect starts, the
values would come from last known information: not automated (hand-made copy)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

TEXT = "Enchanted creature is a copy of the chosen creature."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import selectors

    if ability.text.strip() != TEXT:
        return None
    return {"kind": "triggered", "trigger": "event", "optional": False,
            "cond": {"event": "attached", "other": 'sel:{"types":["Creature"]}', "subject": "self"},
            "target": None, "effects": [{"do": "copy_chosen110a", "who": "event", "with": selectors.parse("chosen creature").key()}]}  # type: ignore[union-attr]


def copy_chosen(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import copying, effects

    if not [c for c in effects._cards(plan, ctx, e["with"]) if plan.state.cards[c].zone.endswith(":battlefield")]:
        copying._manual(plan, copying.new_job(ctx, controller=ctx["controller"], objects=[], retarget=False, label=ctx.get("name") or "Copy"),
                        f"{ctx.get('name') or 'Copy'}: the chosen creature isn't on the battlefield, so the copy (of its last known values) isn't automated: make it by hand, then press Done")
        return False
    return copying.become_copy(plan, ctx, {"do": "become_copy", "duration": "while_attached110l", "who": e["who"], "with": e["with"]})


PRIMITIVES = {"copy_chosen110a": copy_chosen}
