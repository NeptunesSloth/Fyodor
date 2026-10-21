"""Bound source-card references delegated to existing graveyard trigger semantics."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

NARCO = "When this card is put into your graveyard from your library, you may put it onto the battlefield."
BRIDGE = ("When a creature is put into an opponent's graveyard from the battlefield, "
          "if this card is in your graveyard, exile this card.")


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'triggered' or ability.text not in (NARCO, BRIDGE):
        return None
    from app.rules import scripts

    text = (ability.text.replace('put it onto the battlefield', 'put this card onto the battlefield')
            if ability.text == NARCO else ability.text.replace('exile this card', 'exile this creature'))
    return scripts.define(replace(ability, text=text), ch)
