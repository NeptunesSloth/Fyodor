"""A permanent meeting several printed tap criteria still produces one native trigger."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

TEXT = ("Whenever a Swamp, Mountain, black permanent, or red permanent becomes tapped, "
        "this enchantment deals 1 damage to that permanent's controller.")


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    from app.rules import scripts, selectors

    native = scripts.define(replace(ability, text=TEXT.replace(
        'a Swamp, Mountain, black permanent, or red permanent', 'a permanent')), ch)
    if native is None:
        return None
    union = selectors.Selector(either=(
        selectors.Selector(types=('Land',), subtypes=('Swamp','Mountain')).key(),
        selectors.Selector(colors=('B','R')).key(),
    ))
    return {**native, 'cond': {**native['cond'], 'sel': union.key()}}
