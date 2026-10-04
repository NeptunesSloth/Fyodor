"""Rooms (wave 18G, CR 709.5): split permanent cards with one shared type line, and their doors.

A Room permanent has a "left half unlocked" and a "right half unlocked" designation (709.5c), here
``RulesState.unlocked`` (rules object -> [door numbers], 1 = left, 2 = right). A locked door's name, mana cost and rules text are
not there (709.5): ``characteristics.with_doors`` / ``copying.with_level`` read the designations, ``scripts.definitions`` leaves
out a locked door's abilities (``AbilityText.section`` is the door, as it is the level for a Class).

* entering: a Room spell cast as one half enters with that door unlocked (709.5d); one that enters any other way has neither;
* the unlock cost (116.2m, 709.5e): a special action, ``unlock_door``, pay a locked half's mana cost in your main phase with an
  empty stack;
* "When you unlock this door, …" (709.5h) is a ``designation`` event (``counter="unlocked"``) read by ``designations.facts``.
"""
from __future__ import annotations

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import emit
from app.game.state import STACK
from app.rules import characteristics as chars
from app.rules import mana as M
from app.rules.plan import Plan, require_no_decision, require_priority


def doors_of(plan: Plan, card_id: str) -> list[int]:
    return plan.rules.unlocked.get(plan.oid(card_id), [])


def unlock(plan: Plan, card_id: str, door: int) -> None:
    """709.5f: the permanent is given the unlocked designation of ``door``; abilities that trigger when that door is unlocked do
    so however it got the designation (709.5h)."""
    card = plan.state.cards[card_id]
    oid = plan.oid(card)
    plan.rules.unlocked[oid] = sorted({*plan.rules.unlocked.get(oid, []), door})
    emit(plan.state, "designation", counter="unlocked", card=card_id, object_id=oid, amount=door, player=card.controller)


def entered(plan: Plan, card_id: str) -> None:
    """709.5d: a Room permanent that was cast as one half has that half's door unlocked (the half is the face it was cast with)."""
    card = plan.state.cards.get(card_id)
    data = plan.info.get(card.card_id) if card is not None and card.card_id and card.zone.endswith(":battlefield") else None
    if data is not None and chars.room(data):
        unlock(plan, card_id, card.face + 1)  # type: ignore[union-attr]


def unlock_action(plan: Plan, a: A.UnlockDoor) -> None:
    """116.2m, 709.5e: a special action any time you have priority in your main phase with an empty stack; it doesn't use the stack."""
    from app.rules.casting import MAIN_PHASES, Purpose, can_pay, pay, pay_from_pool, payment_mode

    require_no_decision(plan)
    require_priority(plan)
    state = plan.state
    card = state.cards.get(a.card_id)
    data = plan.info.get(card.card_id) if card is not None and card.card_id else None
    if card is None or data is None or not chars.room(data) or card.controller != plan.actor or not card.zone.endswith(":battlefield"):
        raise ActionError("Unlock a door of a Room you control")
    if state.turn.active_player != plan.actor or state.turn.phase not in MAIN_PHASES or state.zones.get(STACK):
        raise ActionError("Unlock a door in your main phase, with the stack empty")
    if a.door in doors_of(plan, card.id):
        raise ActionError("That door is already unlocked")
    half = chars.half_from_data(data, a.door - 1)
    cost = M.parse_cost(half.mana_cost)
    why = f"paid {cost.text()} to unlock {half.name}"
    purpose = Purpose(ability_of=half)
    if payment_mode(plan, plan.actor) == "self":
        pay_from_pool(plan, plan.actor, cost, why, purpose=purpose)
    else:
        if not can_pay(state, plan.actor, cost, plan.info, purpose=purpose):
            raise ActionError(f"Not enough mana to pay {cost.text()}")
        pay(plan, plan.actor, cost, why, sources=a.sources, purpose=purpose)
    unlock(plan, card.id, a.door)
    plan.rules.passed = []
