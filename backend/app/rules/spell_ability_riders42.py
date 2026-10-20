"""Bounded actual spell abilities that continue on the resulting permanent (400.7)."""
from __future__ import annotations

from typing import Any

from app.rules.plan import Plan

_TEXT={'dies_exile_self':'When this creature dies, exile it.'}


def grant(plan: Plan, card_id: str, rider: dict[str,Any], controller: str) -> None:
    if rider.get('kind')!='granted_ability' or rider.get('ability') not in _TEXT:
        return
    from app.rules import layers

    layers.add_effect(plan,affected=[plan.oid(card_id)],layer='6',source=rider.get('src'),controller=controller,
                      add_abilities=[_TEXT[rider['ability']]],duration='permanent',label=rider.get('name') or 'Granted spell ability')
