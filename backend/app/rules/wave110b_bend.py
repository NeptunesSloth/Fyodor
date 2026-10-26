"""-- (wave 110B) -- "Whenever you waterbend, earthbend, firebend, or airbend" (Avatar Aang), "if you've done all four this turn".

* 701.65b airbend: exiles one or more objects; 701.66b earthbend: the delayed trigger is created; 701.67c waterbend: a waterbend cost is
  paid; 702.189b firebend: a firebending ability resolves. Each emits one ``designation`` event ``bend110b:<kind>``, which also leaves a
  turn fact (``bend110b_<kind>``) for "all four this turn" (608.2i).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rules.plan import Plan

KINDS = ("water", "earth", "fire", "air")


def note(plan: Plan, pid: str, kind: str) -> None:
    from app.game.rules_state import emit

    emit(plan.state, "designation", counter=f"bend110b:{kind}", player=pid)
