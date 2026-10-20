"""Inject internal rider metadata into legal printed test mana abilities.

CR 605.1a excludes printed library-moving abilities. This scoped fixture tests
CPS below that classifier; production abilities may draw through replacements.
"""
from dataclasses import replace

from app.rules import mana


def inject_draw_riders(monkeypatch):
    original = mana.parse_mana_ability

    def parse(text, *args, **kwargs):
        ability = original(text, *args, **kwargs)
        name = kwargs.get('card_name', '')
        if ability is not None and name.startswith('CPS Test'):
            draws = 2 if 'Two Draws' in name else 1
            return replace(ability, riders=((('draw', 1),) * draws) + ability.riders)
        return ability

    monkeypatch.setattr(mana, 'parse_mana_ability', parse)
