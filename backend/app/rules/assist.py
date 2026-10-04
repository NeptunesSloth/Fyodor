"""-- casting extras (wave 18E) -- assist (CR 702.132), researched against the stored Comprehensive Rules (2026-09-25).

* 702.132a — if the total cost to cast a spell with assist includes generic mana, before the caster activates mana abilities (601.2g) they
  may choose another player; that player may pay for any amount of the generic mana in the spell's total cost, before the caster begins
  to pay (601.2h). The caster asks (``CastSpell.assist``: the helper's id, or "" for no one), the helper answers how much (``assist_amount``,
  0 up to what they can pay); both are decisions that resume the cast, like a mode or target choice. The helper's mana is paid by the
  engine from their own sources (the solver picks, as AUTO payment does for anyone) all at once with the caster's payment (601.2h: nothing
  moves unless the whole cost can be paid).

Both questions are private to the person choosing (the table sees only who is choosing), and the helper's mana pool and sources are only
read to bound their answer — the options they see are theirs alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules import mana as M

if TYPE_CHECKING:
    from app.game import actions as A
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

WAITING = object()  # a question was asked: the cast resumes with its answer


def supported(line: str) -> bool:
    return line.strip().rstrip(".").lower() == "assist"


def announce(plan: Plan, a: A.CastSpell, card: CardInstance, ch: Characteristics, cost: M.ManaCost) -> Any:
    """→ (helper, generic mana they pay) / (None, 0), or WAITING while a question is open."""
    from app.rules.casting import Purpose, can_pay
    from app.rules.plan import decide

    others = [p for p in plan.live() if p != plan.actor]
    if cost.generic < 1 or not others or a.assist == "":
        return None, 0
    resume = {"intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}), "caster": plan.actor}
    if a.assist is None:
        decide(plan, player=plan.actor, kind="choose_one",
               prompt=f"{ch.name or 'This spell'} has assist: choose another player who may pay for its generic mana, or no one",
               options=[*(DecisionOption(id=p, label=plan.name(p)) for p in others), DecisionOption(id="", label="No one")],
               resume={"step": "assist", "field": "assist", **resume}, source=None)
        return WAITING
    if a.assist not in others:
        raise ActionError("Choose another player still in the game to help pay (assist)")
    helper = a.assist
    if a.assist_amount is None:
        top = max(k for k in range(cost.generic + 1)
                  if k == 0 or can_pay(plan.state, helper, M.ManaCost(generic=k), plan.info,
                                       purpose=Purpose(spell=ch, zone=card.zone, player=helper)))
        if top == 0:
            return None, 0  # (nothing they could pay: no question to ask them)
        decide(plan, player=helper, kind="choose_one",
               prompt=f"{plan.name(plan.actor)} asks you to help pay for {ch.name or 'a spell'} (assist): how much of its generic mana will you pay?",
               options=[DecisionOption(id=str(k), label=f"Pay {k}" if k else "Pay none") for k in range(top + 1)],
               resume={"step": "assist", "field": "assist_amount", **resume}, source=None)
        return WAITING
    return helper, max(0, min(a.assist_amount, cost.generic))


def pay(plan: Plan, helper: str, amount: int, card: CardInstance, ch: Characteristics) -> None:
    """601.2h: the helper pays the generic mana they offered, from their own sources, with the rest of the cost."""
    from app.rules.casting import Purpose
    from app.rules.casting import pay as pay_mana

    if amount <= 0:
        return
    pay_mana(plan, helper, M.ManaCost(generic=amount), f"paid {amount} to help cast {ch.name or 'a spell'} (assist)",
             purpose=Purpose(spell=ch, zone=card.zone, player=helper))
    plan.note(f"{plan.name(helper)} pays {amount} of {ch.name or 'the spell'}'s generic mana (assist)", actor=helper)


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The answer given: the cast starts over with it (an answer of no one is ``assist=""``)."""
    from app.game import actions as A
    from app.rules.engine import INTENTS

    intent = A.parse_action(d.resume["intent"])
    if d.resume["field"] == "assist":
        intent.assist = chosen[0]  # type: ignore[union-attr]
    else:
        intent.assist_amount = int(chosen[0])  # type: ignore[union-attr]
    plan.rules.priority = d.resume["caster"]
    plan.rules.passed = []
    prev, plan.actor = plan.actor, d.resume["caster"]  # (the helper answered: the cast goes on as its caster's)
    try:
        INTENTS[intent.type](plan, intent)
    finally:
        plan.actor = prev
