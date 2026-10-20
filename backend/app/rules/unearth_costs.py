"""CR 702.84a: unearth is an activated ability with a mana or energy cost."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.rules import costs
from app.rules.oracle import AbilityText, strip_reminders

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics

_MANA = re.compile(r'^unearth (?P<cost>(?:\{[^}]+\})+)$', re.I)
_ENERGY = re.compile(r'^unearth—(?P<cost>Pay (?:\w+ )?\{E\}(?:\{E\})*)$', re.I)


def parse(line: str) -> str | None:
    line = strip_reminders(line).strip().rstrip('.')
    if m := _MANA.fullmatch(line):
        return m['cost']
    if (m := _ENERGY.fullmatch(line)) is not None:
        cost = costs.parse_ability_cost(m['cost'])
        if not cost.unsupported and cost.components and all(c.kind == costs.PAY_ENERGY for c in cost.components):
            return m['cost']
    return None


def of(ch: Characteristics, index: int) -> str | None:
    return next((found for a in ch.abilities if a.index == index and a.kind == 'keywords' and 'unearth' in a.keywords
                 and (found := parse(a.text)) is not None), None)


def ability(index: int, cost: str) -> AbilityText:
    return AbilityText(index=index, kind='activated', cost=cost,
                       text=f'{cost}: Return this card from your graveyard to the battlefield. Activate only as a sorcery.')
