"""The hand-cast enter trigger excludes Giant, Wizard, and land permanents."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('When this creature enters, if you cast it from your hand, return all permanents to their owners\' hands '
        'except for Giants, Wizards, and lands.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text='When this creature enters, if you cast it from your hand, you gain 1 life.'), ch)
    if native is None:
        return None
    effects = native.get('effects') or []
    if len(effects) != 2 or effects[0].get('do') != 'only_if':
        return None
    returned = selectors.Selector(not_types=('Land',), not_subtypes=('Giant', 'Wizard')).key()
    return {**native, 'effects': [effects[0], {'do': 'bounce', 'who': returned}]}
