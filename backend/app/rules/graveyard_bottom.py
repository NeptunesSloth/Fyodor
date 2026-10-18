"""-- trigger other (wave 52B) -- "Up to one target player puts all the cards from their graveyard on the bottom of their library in a random order." (Endurance).

* 401.4: the cards are put on the bottom of the library in a random order, which the table's randomness picks without anyone being able to read it
  (effects.bottom_at_random: one move, recorded, so a replay or a load puts them in the same order). Nothing about the order is shown.
* 115.1d: "up to one target player" may name no one; the target is chosen as the ability goes on the stack, and it is the target player who puts the cards there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]


def graveyard_bottom(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import bottom_at_random, target_refs

    for ref in target_refs(ctx, e.get("who", "target")):
        pid = ref["id"]
        cards = list(plan.state.zones.get(f"{pid}:graveyard", []))
        if pid in plan.state.players and pid in plan.live() and cards:
            plan.note(f"{plan.name(pid)} puts {len(cards)} card(s) from their graveyard on the bottom of their library in a random order")
            bottom_at_random(plan, pid, cards)
    return True


PRIMITIVES: dict[str, Any] = {"graveyard_bottom": graveyard_bottom}
