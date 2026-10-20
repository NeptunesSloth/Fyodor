"""Exact durable previous-combat declaration receipts."""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.game.rules_state import CombatMemory, CombatReceipt

if TYPE_CHECKING:
    from app.rules.plan import Plan



def begin(memory: CombatMemory, player: str, turn: int, combat: int) -> None:
    if memory.current is not None:
        old = memory.current
        if (old.player, old.turn, old.combat) == (player, turn, combat):
            return
        memory.previous[old.player] = old
        memory.known_empty = [p for p in memory.known_empty if p != old.player]
    memory.current = CombatReceipt(player=player, turn=turn, combat=combat)


def declared(memory: CombatMemory, player: str, turn: int, combat: int,
             attackers: list[str], targets: list[str], players: set[str]) -> bool:
    receipt = memory.current
    if receipt is None or (receipt.player, receipt.turn, receipt.combat) != (player, turn, combat):
        return False
    for oid, target in zip(attackers, targets, strict=True):
        if target in players:
            seen = receipt.players_attacked.setdefault(oid, [])
            if target not in seen:
                seen.append(target)
    return True


def previous_players(memory: CombatMemory, player: str, source_oid: str) -> set[str] | None:
    receipt = memory.previous.get(player)
    if receipt is not None:
        return set(receipt.players_attacked.get(source_oid) or [])
    return set() if player in memory.known_empty else None


def combat_began(plan: Plan) -> None:
    memory = plan.rules.combat_memory
    if memory is None:
        memory = plan.rules.combat_memory = CombatMemory()
    begin(memory, plan.active, plan.state.turn.number, plan.rules.combats)
