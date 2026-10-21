"""A control recipient, rather than the trigger's controller, puts the following counter."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('At the beginning of your end step, target opponent gains control of ~ '
        'and puts a charge counter on it.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    native = scripts.define(replace(ability, text='At the beginning of your end step, target opponent gains control of ~.'), ch)
    if native is None:
        return None
    return {**native, 'effects': [*native['effects'],
            {'do': 'add_counters', 'who': 'self', 'kind': 'charge', 'n': 1, 'by': 'target'}]}
