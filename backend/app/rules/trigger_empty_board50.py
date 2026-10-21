"""The exact empty-board wording delegates to the native state-trigger grammar."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = 'When no creatures are on the battlefield, sacrifice this enchantment.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    return scripts.define(replace(ability, text=TEXT.replace('no creatures are', 'there are no creatures')), ch)
