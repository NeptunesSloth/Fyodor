"""The selected half's base characteristics on the stack (709.3a, 715.3b).

X remains absent from this base view. Callers that need an announced mana value
still add X using their existing contracts.
"""
from __future__ import annotations

from typing import Any

from app.rules.characteristics import Characteristics


def apply(state: Any, card: Any, ch: Characteristics, info: Any, *, snapshot: Any = None) -> Characteristics:
    if info is None or state.rules is None or card.zone != 'stack' or card.face_down or card.ability is not None:
        return ch
    from app.game.rules_state import copy_recipe_of
    from app.rules import characteristics, copying

    oid = snapshot.object_id if snapshot is not None else state.rules.object_id(card.id)
    memory = state.rules.stack_lki.get(oid)
    entry = memory.entry if memory is not None else state.rules.stack.get(card.id)
    if entry is None or entry.kind != 'spell' or ch.name == entry.name:
        return ch
    recipe = snapshot.copy_recipe if snapshot is not None else copy_recipe_of(state.rules, oid)
    printing = recipe.printing if recipe is not None and recipe.printing else card.card_id
    data = info.get(printing) if printing else None
    if data is None or data.get('layout') not in characteristics.HALVES:
        return ch
    for index, face in enumerate(data.get('faces') or []):
        if face.get('name') != entry.name:
            continue
        selected = characteristics.half_from_data(data, index)
        for exception in recipe.excepts if recipe is not None else ():
            selected = copying._apply(selected, exception)
        return selected
    # Both names denote the fused split spell, which keeps the combined base.
    return ch
