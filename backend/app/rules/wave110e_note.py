"""-- wave 110E -- "Note the mana value of each card as it's put into exile. ~'s power is equal to the greatest number noted for it this turn." (Bell Borca)

400.1 / 406: a card put into exile from another zone (history's ``exile`` fact: never a token). The note is made by a permanent with the line, only while it is on
the battlefield (an ability of a permanent works only there, 113.6), and kept per rules object: ``RulesState.noted110e[oid] = [turn, batch]`` is where it arrived; the
value is the greatest ``mv110e`` of this turn's exile facts after that (history keeps them for the turn, so it is 0 on any other turn).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rules.plan import Plan

LINE = "Note the mana value of each card as it's put into exile."
POWER = "Bell Borca, Spectral Sergeant's power is equal to the greatest number noted for it this turn."


def entered(plan: Plan, card_id: str) -> None:
    """after_entry: where in this turn's event order a permanent with the line arrived (it notes only what is exiled afterwards)."""
    card = plan.state.cards[card_id]
    if any(a.text == LINE for a in plan.ch(card).abilities):
        plan.rules.noted110e[plan.oid(card)] = [plan.state.turn.number, max([plan.rules.batch, *(e.batch for e in plan.rules.events)])]  # (a pending event has batch + 1)


def greatest(plan: Plan, oid: str) -> int:
    """The greatest mana value among cards put into exile this turn since it arrived (0: none). A permanent that arrived on an earlier turn noted all of them."""
    from app.rules import history

    turn, batch = plan.rules.noted110e.get(oid, [0, 0])
    since = batch if turn == plan.state.turn.number else -1
    return max((f.mv110e for f in history.log_for(plan).facts if f.kind == "exile" and f.batch > since), default=0)
