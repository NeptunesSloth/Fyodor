"""Four native activation watchers whose events include mana abilities."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

TEXTS = frozenset({
    "Whenever you activate an ability of a creature, draw a card. This ability triggers only once each turn.",
    "Whenever an opponent activates an ability of an artifact they control, ~ deals 1 damage to that player.",
    "Whenever you activate an ability of an Elemental, ~ gets +1/+0 until end of turn.",
    "Whenever you activate an ability of a Sarkhan planeswalker, ~ deals 1 damage to any target.",
})


def supported(ability: AbilityText, ch: Characteristics) -> bool:
    from app.rules import scripts

    return ability.kind == 'triggered' and scripts.self_text(ability.text, ch.name) in TEXTS
