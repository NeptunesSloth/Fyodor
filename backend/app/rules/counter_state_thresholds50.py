"""The printed tide threshold is a native state trigger, independent of entering the state."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = 'Whenever there are four or more tide counters on ~, remove all tide counters from it.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    return scripts.define(replace(ability, text=TEXT.replace('Whenever ', 'When ', 1)), ch)
