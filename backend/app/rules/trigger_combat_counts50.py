"""Exact native combat quantities and conditions checked only at the event."""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

AUROCHS = "Whenever this creature attacks, it gets +1/+0 until end of turn for each other attacking Aurochs."
CAVALRY = ("Whenever this creature attacks or blocks while you control a Dinosaur, "
           "this creature gets +1/+1 until end of turn.")


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'triggered' or ability.text not in (AUROCHS, CAVALRY):
        return None
    # Other Aurochs already parse natively. This source's name collides with the subtype word.
    if ability.text == AUROCHS and ch.name != 'Aurochs':
        return None
    from app.rules import conditions, scripts, selectors

    text = ("Whenever this creature attacks, it gets +1/+0 until end of turn." if ability.text == AUROCHS else
            "Whenever this creature attacks or blocks, this creature gets +1/+1 until end of turn.")
    native = scripts.define(replace(ability, text=text), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    if ability.text == AUROCHS:
        effects = out.get('effects') or []
        if len(effects) != 1 or effects[0].get('do') != 'pump':
            return None
        effects[0]['p'] = {'count': selectors.Selector(subtypes=('Aurochs',), attacking=True, other=True).key()}
    else:
        condition = conditions.parse('you control a Dinosaur', objects=True)
        if condition is None:
            return None
        out['cond'] = {'event': 'either', 'conds': [
            {'event': event, 'subject': 'self', 'while': condition} for event in ('attack', 'block')]}
    return out
