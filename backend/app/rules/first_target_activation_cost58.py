"""First qualifying activated ability costs use complete turn history and frozen targets."""
from __future__ import annotations

from typing import Any

KEY = "activated:{player}:controlled_creature_target"


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text != "The first activated ability you activate during your turn that targets a creature you control costs {2} less to activate.":
        return None
    return {"kind": "static", "static": "ability_cost_modifier", "who": "you", "filter": None,
            "delta": -2, "floor": False, "first_controlled_creature_target58": True, "effects": []}


def qualifies(state: Any, player: str, targets: tuple[str, ...], info: Any) -> bool:
    from app.rules.plan import Plan

    view = Plan.view(state, player, info)
    return any((card := state.cards.get(cid)) is not None and card.zone.endswith(":battlefield")
               and card.controller == player and "Creature" in view.ch(card).types for cid in targets)


def available(state: Any, player: str, target: str | None, targets: tuple[str, ...] | None, info: Any) -> bool:
    rules = state.rules
    if rules is None or state.turn.active_player != player or rules.target_activation_history_turn != state.turn.number:
        return False
    if rules.once_per_turn.get(KEY.format(player=player)) == state.turn.number:
        return False
    if target == "?":
        return True  # Optimistic preview only; actual announced targets recompute the total cost.
    return qualifies(state, player, targets if targets is not None else ((target,) if target else ()), info)


def record(plan: Any, qualified: bool | None) -> None:
    if qualified:
        plan.rules.once_per_turn[KEY.format(player=plan.actor)] = plan.state.turn.number
