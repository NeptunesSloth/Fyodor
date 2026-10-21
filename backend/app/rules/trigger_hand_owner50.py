"""Hand-destination triggers refer to the returned permanent's owner."""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

TEXT = "Whenever a permanent is returned to a player's hand, that player discards a card."
BASE = "Whenever a permanent is returned to hand, that player discards a card."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    from app.rules import scripts

    native = scripts.define(replace(ability, text=BASE), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    effects = out.get('effects') or []
    if len(effects) != 1 or effects[0].get('do') != 'discard':
        return None
    effects[0]['who'] = 'ref:event.owner'
    return out
