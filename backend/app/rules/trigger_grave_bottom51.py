"""A card in an opponent's graveyard belongs to that graveyard's owner (CR400.3)."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

TEXT = "When this creature enters, put target card from an opponent's graveyard on the bottom of their library."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    from app.rules import scripts

    return scripts.define(replace(ability, text=TEXT.replace('their library', "its owner's library")), ch)
