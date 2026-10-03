"""-- hand size (wave 4J) -- "You have no maximum hand size." (Reliquary Tower, Thought Vessel, Decanter of Endless
Water). Researched against CR 2026-09-25.

* 402.2: each player has a maximum hand size, normally seven; as part of their cleanup step (514.1) the active player
  discards down to it. A static ability of a permanent saying its controller has no maximum hand size removes that
  discard while the permanent is on the battlefield under their control (611.3a: a static ability's effect applies
  while the object is on the battlefield).
* Only that exact wording: a changed maximum ("The chosen player's maximum hand size is four", "Your maximum hand
  size is increased by one") and "for the rest of the game" from a resolving spell stay manual.

Read by the cleanup step (app/rules/engine.cleanup_step).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

NO_MAXIMUM = "no_max_hand"


def static_definition(text: str) -> dict[str, Any] | None:
    if text.strip() == "You have no maximum hand size.":
        return {"kind": "static", "static": NO_MAXIMUM, "effects": []}
    return None


def no_maximum(plan: Plan, player: str) -> bool:
    """Whether a permanent ``player`` controls gives them no maximum hand size (402.2)."""
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    for c in plan.state.cards.values():
        if c.controller != player or not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) \
                or plan.manual(c):
            continue
        ch = plan.ch(c)
        skip = conditional_lines(ch)  # (a leveler's / Class's level lines: the level isn't tracked)
        if any(i not in skip and d.get("kind") == "static" and d.get("static") == NO_MAXIMUM
               for i, d in scripts.definitions(ch).items()):
            return True
    return False
