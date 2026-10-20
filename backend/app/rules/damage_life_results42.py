"""Damage-result restriction, separate from preventing damage or life loss."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(text: str) -> dict[str, Any] | None:
    if text == "As long as you're the monarch, damage doesn't cause you to lose life.":
        return {'kind':'static','static':'damage_life_result','who':'you','monarch':True,'effects':[]}
    return None


def why_not(plan: Plan, player: str) -> str | None:
    """Read only when converting already dealt damage into ordinary life loss.

    The caller preserves the original damage event, poison, commander records,
    lifelink and triggers. Explicit life loss and life payment never call this.
    """
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    for card in plan.state.cards.values():
        if card.controller!=player or not card.zone.endswith(':battlefield') or card.face_down or not plan.in_game(card) or plan.manual(card):
            continue
        ch=plan.ch(card)
        skip=conditional_lines(ch)
        for index,d in scripts.definitions(ch).items():
            if index in skip or d.get('kind')!='static' or d.get('static')!='damage_life_result':
                continue
            if d.get('who')=='you' and (not d.get('monarch') or plan.state.table.monarch==player):
                return ch.name or card.name or 'an effect'
    return None
