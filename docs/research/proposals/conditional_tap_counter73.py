"""Exact chosen-target wording retains native conditional next-untap duration."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text != ("When ~ enters, choose target creature you don't control and tap it. If you control a creature with "
                "a counter on it, the chosen creature doesn't untap during its controller's next untap step."):
        return None
    return scripts.define(replace(ability, text=text.replace('choose target', 'tap target').replace(' and tap it.', '.')
                                  .replace('the chosen creature', 'that creature')), ch)
