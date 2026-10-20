"""Inject a structured draw rider to test continuations, without inventing a legal Oracle mana ability.

CR 605.1a excludes an ability whose cost or effect moves a card to/from a library
(replacement effects are ignored when classifying it). Tests print a legal mana
ability and explicitly inject this rider below the classifier. This isolates the
persistent payment machinery and makes no card-automation or eligibility claim.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any


def inject_mana_draw_rider(monkeypatch: Any, names: frozenset[str] | set[str]) -> None:
    """Prepend one draw before the selected synthetic sources' existing structured riders."""
    from app.rules import casting

    original = casting.mana_abilities

    def abilities(state: Any, card: Any, info: Any) -> Any:
        found = original(state, card, info)
        if card.name in names:
            return [(index, replace(ability, riders=(("draw", 1), *ability.riders))) for index, ability in found]
        return found

    monkeypatch.setattr(casting, 'mana_abilities', abilities)
