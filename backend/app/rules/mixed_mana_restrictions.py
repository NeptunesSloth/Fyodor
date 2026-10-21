"""Mixed spell, ability and special-action alternatives for restricted mana."""
from __future__ import annotations

from typing import Any


def parse(sentence: str) -> dict[str, Any] | None:
    from app.rules.selectors import OUTLAW_TYPES

    forms: dict[str, dict[str, Any]]={
        'Spend this mana only to cast outlaw spells or activate abilities of outlaw sources':
            {'cast':[{'any_subtypes':OUTLAW_TYPES.split('|')}], 'ability':[{'any_subtypes':OUTLAW_TYPES.split('|')}]},
        'Spend this mana only to cast an enchantment spell, unlock a door, or turn a permanent face up':
            {'cast':[{'types':['Enchantment']}], 'special':['unlock','turn_up']},
        'Spend this mana only to pay a disturb cost or cast an instant or sorcery spell':
            {'alternative':['disturb'],'cast':[{'types':['Instant']},{'types':['Sorcery']}]},
        'Spend this mana only to cast a colorless spell, activate an ability of a colorless permanent, or pay a cost that contains {C}':
            {'cast':[{'color':'colorless'}],'ability':[{'color':'colorless','on_battlefield':True}],'cost_colorless':True},
        'Spend this mana only to cast face-down spells or to turn creatures face up':
            {'cast':[{'face_down':True}],'special':['turn_up']},
        'Spend this mana only to cast a face-down creature spell, pay a mana cost to turn a manifested creature face up, or pay a morph cost':
            {'cast':[{'face_down':True,'types':['Creature']}],'turn_up_methods':['morph','manifest_mana']},
    }
    return forms.get(sentence.strip().rstrip('.'))
