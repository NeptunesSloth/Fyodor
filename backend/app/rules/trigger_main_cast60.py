"""Dovin's Acuity checks the native main-phase predicate only when a spell is cast."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ("Whenever you cast an instant spell during your main phase, "
        "you may return this enchantment to its owner's hand.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text=TEXT.replace(' during your main phase', '')), ch)
    if native is None:
        return None
    return {**native, 'cond': {**native['cond'], 'while': {'main_phase': 'yours'}}}
