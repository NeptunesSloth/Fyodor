"""-- entry control (wave 110A) -- "This permanent enters under the control of an opponent of your choice."

614.12: a replacement that applies as the permanent enters; 110.2: it enters under the chosen player's control. The opponent is
chosen as it enters (614.12a: an "enters_choice" of an opponent, no question with one opponent left). A permanent spell is
given to that player while still on the stack (the one rule-visible difference: it enters under them, so "enters" triggers and
replacements see them); any other entry is fixed up right after it (``after_entry``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

TEXT = "~ enters under the control of an opponent of your choice."


def definition(text: str) -> dict[str, Any] | None:
    if text != TEXT:
        return None
    return {"kind": "replacement", "replacement": "enters_choice", "control": "opponent",
            "effects": [{"do": "choose_value", "who": "you", "what": "opponent", "remember": True}]}


def defs(plan: Plan, card: CardInstance) -> bool:
    from app.rules import scripts

    return any(d.get("control") == "opponent" for d in scripts.definitions(plan.ch(card)).values() if d["kind"] == "replacement")


def give(plan: Plan, card_id: str, choices: dict[str, str] | None) -> None:
    """Set the controller of a stack spell / entered permanent to the opponent chosen as it enters."""
    card = plan.state.cards.get(card_id)
    who = (choices or {}).get("opponent")
    if card is None or not who or who not in plan.state.players or card.controller == who or not defs(plan, card):
        return
    plan.do({"type": "set_controller", "card_ids": [card_id], "player": who}, actor=card.controller)
