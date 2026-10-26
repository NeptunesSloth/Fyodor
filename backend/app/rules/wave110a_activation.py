"""Tezzeret, Betrayer of Flesh: "The first activated ability of an artifact you activate each turn costs {2} less to
activate." (601.2f via 602.2b; mana abilities count as activations, 605.1a). History = TurnFact "artifact_act110a"."""
from __future__ import annotations

from typing import Any

TEXT = "The first activated ability of an artifact you activate each turn costs {2} less to activate."
KIND = "artifact_act110a"


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text != TEXT:
        return None
    return {"kind": "static", "static": "ability_cost_modifier", "who": "you", "filter": None,
            "delta": -2, "floor": False, "first_artifact110a": True, "effects": []}


def note(plan: Any, och: Any, actor: str, oid: str) -> None:
    """Called from triggers.activated: remember that `actor` activated an ability of an artifact this turn."""
    if "Artifact" not in och.types:
        return
    from app.game.rules_state import TurnFact, turn_log_now

    if (log := turn_log_now(plan.state)) is not None:
        log.facts.append(TurnFact(kind=KIND, player=actor, object_id=oid))


def available(state: Any, player: str, ch: Any) -> bool:
    from app.game.rules_state import turn_log_now

    if "Artifact" not in ch.types or state.rules is None:
        return False
    log = turn_log_now(state)
    return log is None or not any(f.kind == KIND and f.player == player for f in log.facts)


def component(part: str) -> Any:
    """Tectonic Split: "sacrifice half the lands you control, rounded up" (118.3: a cost needs that many; rounding up per the card)."""
    if part.lower() != "sacrifice half the lands you control, rounded up":
        return None
    from app.rules import costs

    key = costs._selector("lands you control", zone="battlefield")
    return costs.CostComponent(costs.SACRIFICE, selector=key, half=True, text=part) if key else None
