"""The exact second-draw token and counter instruction uses two ordinary native effects."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('Whenever you draw your second card each turn, create a 2/1 black Villain creature token '
        'with menace and put a plan counter on this enchantment.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    return scripts.define(replace(ability, text=TEXT.replace(' and put a plan counter', '. Put a plan counter')), ch)
