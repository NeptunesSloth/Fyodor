"""Exact destination-graveyard triggers bind owners rather than controllers."""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

MORTUARY = "Whenever a creature is put into your graveyard from the battlefield, put that card on top of your library."
PATRON = "Whenever a permanent is put into an opponent's graveyard, that player loses 1 life."
LIABILITY = "Whenever a nontoken permanent is put into a player's graveyard from the battlefield, that player loses 1 life."
VOID = "Whenever another card is put into a graveyard from anywhere, exile that card."
MEASURE = "Whenever another card is put into your graveyard from anywhere, target opponent gains control of this enchantment."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'triggered' or ability.text not in (MORTUARY, PATRON, LIABILITY, VOID, MEASURE):
        return None
    from app.rules import events, scripts, selectors

    base = "Whenever a creature dies, you gain 1 life."
    native = scripts.define(replace(ability, text=base), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    text = ability.text
    clause = {
        MORTUARY: 'a creature is put into your graveyard from the battlefield',
        PATRON: "a permanent is put into an opponent's graveyard from the battlefield",
        LIABILITY: "a nontoken permanent is put into a player's graveyard from the battlefield",
        VOID: 'a card is put into a graveyard from anywhere',
        MEASURE: 'a card is put into your graveyard from anywhere',
    }[text]
    condition = events.parse_condition(clause)
    if condition is None:
        return None
    if text in (VOID, MEASURE):
        condition = {**condition, 'sel': selectors.replace(selectors.from_key(condition['sel']), other=True).key()}
    out['cond'] = condition
    if text == MORTUARY:
        out['effects'] = [{'do': 'to_library', 'who': 'ref:event.new', 'place': 'top'}]
    elif text == VOID:
        out['effects'] = [{'do': 'exile', 'who': 'ref:event'}]
    elif text == MEASURE:
        out.update(scripts.target_fields('opponent'))
        out['effects'] = [{'do': 'gain_control', 'who': 'self', 'to': 'target'}]
    else:
        out['effects'] = [{'do': 'lose_life', 'who': 'ref:event.owner', 'n': 1}]
    return out
