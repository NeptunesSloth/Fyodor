"""Damage-sized target groups retain the native event amount and player binding."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ("Whenever ~ deals combat damage to a player, return up to that many target permanents "
        "that player controls to their owner's hand.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    # Existing where-bound target groups read the actual damage event at target
    # announcement and preserve that bound through copies, responses and saves.
    native_text = ability.text.replace('up to that many', 'up to X')
    native_text = native_text.removesuffix('.') + ', where X is the damage dealt.'
    return scripts.define(replace(ability, text=native_text), ch)
