"""CR 601.2c, 608.2d: a conditional, independently optional targeted instruction."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    original = ('Exile target artifact or enchantment. If you cast this spell during your main phase, '
                'you may exile up to one other target artifact or enchantment.')
    if body.strip() != original:
        return None
    found = scripts._parse_effects_plain(original.replace('you may exile', 'exile'))
    sel = selectors.parse('artifact or enchantment')
    if found is None or sel is None:
        return None
    effects, target, _ = found
    return ([effects[0], {**effects[1], 'skip': 4},
             {'do': 'only_if', 'cond': {'object': 'target:1', 'is': sel.key()}, 'skip': 3},
             {'do': 'optional_payment', 'who': 'you', 'ask': 'exile the second target', 'cost': '', 'bind': 'optional_exile'},
             {'do': 'only_if', 'cond': {'succeeded': 'optional_exile'}, 'skip': 1}, effects[2]], target, False)
