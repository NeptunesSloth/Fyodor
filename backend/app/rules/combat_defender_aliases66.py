"""Defender-only permissions use the native rule without granting haste or ignoring restrictions."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics


TEXTS = {
    "Enchanted Wall can attack as though it didn't have defender.": "Enchanted creature can attack as though it didn't have defender.",
    "As long as equipped creature has defender, it can attack as though it didn't have defender.": "Equipped creature can attack as though it didn't have defender.",
}


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'static' or ability.text not in TEXTS:
        return None
    from app.rules import statics

    # Without defender this permission changes no action's legality, so the
    # Equipment's printed condition is already implicit in the native rule.
    return statics.parse(TEXTS[ability.text])
