"""Completed final numeric roll receipts for this-turn casting conditions."""
from __future__ import annotations

from typing import Any


def note(plan: Any, events: list[Any], into: Any = None) -> None:
    from app.game.rules_state import TurnFact, turn_log_now

    log = into if into is not None else turn_log_now(plan.state)
    if log is None:
        return
    for event in events:
        if (event.kind == 'designation' and event.counter == 'roll_die'
                and event.turn == plan.state.turn.number and event.player is not None):
            log.facts.append(TurnFact(kind='roll_die', player=event.player, amount=event.amount))


def holds(plan: Any, ctx: dict[str, Any], condition: dict[str, Any], log: Any) -> bool:
    return any(fact.kind == 'roll_die' and fact.player == ctx['controller']
               and fact.amount == condition['result'] for fact in log.facts)
