"""-- planechase -- rolling the planar die with rules automation on (CR 901.9; the table's procedure is app/game/handlers/planechase.py).

901.9: any time the active player has priority and the stack is empty, but only during a main phase of their turn, they may roll the
planar die; the first roll in a turn costs {0}, each further roll that turn {1} more. This is a special action (116.2f): it doesn't use
the stack. Its cost is generic mana, paid the way every cost is at this table (docs/AUTOMATION_UX.md "MANA: you tap your own mana"):
from the mana pool, or, when the pool is short, through the "tap your mana" prompt (CANCEL leaves the table untouched: no roll).

The roll itself is the table's ``planar_roll`` step, resolved on the scratch copy (its face in ``r``) after the payment's steps, so the
intent's compiled steps replay, undo and save exactly. On a manual table (automation off or paused) players roll with ``planar_roll``
and pay by hand.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.game import actions as A
from app.game.errors import ActionError
from app.game.handlers import planechase
from app.game.state import STACK
from app.rules import mana as M
from app.rules import payment_continuations as pc
from app.rules.plan import Plan, require_no_decision, require_priority

MAIN_PHASES = ("main1", "main2")
WHAT = "the planar die"


def roll(plan: Plan, a: A.RollPlanarDie) -> None:
    from app.rules.casting import Purpose, pay_then, payment_step

    require_no_decision(plan)
    require_priority(plan)
    state = plan.state
    if (why := planechase.roll_refusal(state, plan.actor)) is not None:
        raise ActionError(why)
    if state.turn.phase not in MAIN_PHASES or state.zones.get(STACK):
        raise ActionError("You can roll the planar die only in your main phase while the stack is empty")
    cost = M.parse_cost(f"{{{planechase.roll_cost(state)}}}")
    if cost.is_free:  # the first roll this turn
        _roll(plan)
        return
    if payment_step(plan, a, cost, WHAT, purpose=Purpose()):  # (the pool is short: "tap your mana", then this runs again)
        return
    pay_then(plan, plan.actor, cost, f"paid {cost.text()} to roll {WHAT}", sources=a.sources, purpose=Purpose(),
             then=pc.continuation(plan, "planar_die_paid", _Paid(cost.text())))


@dataclass
class _Paid:
    cost: str


def _roll(plan: Plan) -> None:
    plan.do({"type": "planar_roll"})  # (the face is resolved here, on the scratch copy, and recorded in the step)
    plan.rules.passed = []  # (a special action: the player keeps priority, 116.3c; everyone gets to pass again)


def _paid(plan: Plan, frame: _Paid, payment: M.Payment | None) -> None:
    _roll(plan)


pc.register("planar_die_paid", _Paid, _paid)
