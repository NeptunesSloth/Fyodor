"""Bounded conditional counter taxes reuse actual native cast receipts."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText

TEAM = 'Counter target spell unless its controller pays {2}. Counter that spell unless its controller pays {4} instead if this spell was cast using teamwork.'
BEHOLD = 'Counter target spell unless its controller pays {2}. If a Dragon was beheld, counter that spell unless its controller pays {4} instead.'
SURVEIL = 'Choose target spell. Surveil 2, then counter the chosen spell unless its controller pays {1} for each card in your graveyard.'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text in (TEAM, BEHOLD):
        native = scripts.define(replace(ability, text='Counter target spell unless its controller pays {2}. If this spell was cast using teamwork, counter that spell unless its controller pays {4} instead.'), ch)
        assert native is not None
        if text == BEHOLD:
            native['effects'][0]['alt']['cond'] = {'object': 'self', 'cast': {'optional': 'behold'}}
        return native
    if text == SURVEIL:
        return scripts.define(replace(ability, text='Surveil 2. Counter target spell unless its controller pays {1} for each card in your graveyard.'), ch)
    return None
