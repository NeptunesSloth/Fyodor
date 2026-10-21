"""The selected printed Security Rhox alternative carries its own producer rule."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

TEXT = "You may pay {R}{G} rather than pay this spell's mana cost. Spend only mana produced by Treasures to cast it this way."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'static' or ability.text != TEXT:
        return None
    return {'kind': 'static', 'static': 'alt_cost', 'cost': 'pay {R}{G}',
            'producer_requirement': 'treasure_permanent', 'effects': []}
