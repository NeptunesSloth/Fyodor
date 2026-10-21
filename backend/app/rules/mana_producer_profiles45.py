"""Exact printed producer restrictions over typed native payment eligibility."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.rules.mana_requirement_rows import ProducerRequirement

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

WORDINGS = {
    'Spend only mana produced by creatures to cast this spell.': ProducerRequirement.CREATURE_PERMANENT,
    'Spend only mana produced by basic lands to cast this spell.': ProducerRequirement.BASIC_LAND,
}


def requirement(ch: Characteristics) -> ProducerRequirement | None:
    return next((WORDINGS[ability.text] for ability in ch.abilities
                 if ability.kind == 'static' and ability.text in WORDINGS), None)


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'static' or ability.text not in WORDINGS:
        return None
    return {'kind': 'static', 'static': 'mana_producer_restriction',
            'producer': WORDINGS[ability.text].value, 'effects': []}
