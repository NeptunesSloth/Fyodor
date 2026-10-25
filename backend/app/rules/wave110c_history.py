"""-- turn history (wave 110C) -- who destroyed / countered what this turn (608.2i), for the Traps' alternative costs.

* Cobra Trap: "a noncreature permanent under your control was destroyed this turn by a spell or ability an opponent controlled". A spell or ability
  destroys a permanent only through its own "destroy" (701.8a; the card's 2009-10-01 rulings: exile, sacrifice, loss of loyalty and an ability *you*
  control that destroys don't count); the destruction is recorded where the engine carries it out (effects._destroyed), with the controller of the
  spell or ability. The permanent's controller and card types are those it last had on the battlefield (the turn log's departure record).
* Summoning Trap: "a creature spell you cast this turn was countered by a spell or ability an opponent controlled" — recorded where a spell is countered
  (effects.counter_object: 701.6a) with the controller of the spell or ability that countered it; the spell's controller is the player who cast it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import TurnLog
    from app.rules.plan import Plan

CONDITIONS: dict[str, dict[str, Any]] = {
    "a noncreature permanent under your control was destroyed this turn by a spell or ability an opponent controlled": {"history": "destroyed_by_opponent110c"},
    "a creature spell you cast this turn was countered by a spell or ability an opponent controlled": {"history": "countered_by_opponent110c"},
}


def condition(text: str) -> dict[str, Any] | None:
    found = CONDITIONS.get(text)
    return None if found is None else dict(found)


def note_destroyed(plan: Plan, gone: dict[str, str], by: str) -> None:
    """These permanents (card -> the object it was) were destroyed by a spell or ability ``by`` controlled."""
    from app.game.rules_state import TurnFact, turn_log_now

    log = turn_log_now(plan.state)
    if log is not None:
        log.facts += [TurnFact(kind="destroyed", player=by, object_id=oid, source_controller=by) for oid in gone.values()]


def note_countered(plan: Plan, card: Any, by: str) -> None:
    """The spell ``card`` (still on the stack) was countered by a spell or ability ``by`` controlled."""
    from app.game.rules_state import TurnFact, turn_log_now

    log = turn_log_now(plan.state)
    if log is not None:
        log.facts.append(TurnFact(kind="countered", player=card.controller, object_id=plan.oid(card), types=sorted(plan.ch(card).types),
                                  source_controller=by))


def holds(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    from app.rules import history

    me = ctx["controller"]
    if cond["history"] == "countered_by_opponent110c":
        return any(f.kind == "countered" and f.player == me and "Creature" in f.types and f.source_controller not in (None, me) for f in log.facts)
    by = {f.object_id: f.source_controller for f in log.facts if f.kind == "destroyed"}
    return any(d.to == "graveyard" and d.controller == me and by.get(d.object_id) not in (None, me) and "Creature" not in history.departed_types(plan, d)
               for d in log.left)
