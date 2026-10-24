"""Counter conditions for native other-player untaps and attached untap restrictions."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

QUEST = ("As long as there are four or more quest counters on this enchantment, untap all creatures you control "
         "during each other player's untap step.")
GOLD = "Enchanted creature doesn't untap during its controller's untap step if it has a sleep counter on it."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind != 'static':
        return None
    if ability.text == QUEST:
        base = scripts.define(replace(ability, text="Untap all creatures you control during each other player's untap step."), ch)
        cond = {'static': 'self_counter', 'counter': 'quest', 'n': 4}
    elif ability.text == GOLD:
        base = scripts.define(replace(ability, text="Enchanted creature doesn't untap during its controller's untap step."), ch)
        cond = {'static': 'attached_is', 'sel': selectors.Selector(types=('Creature',), extras=('counter:sleep',)).key(),
                'noun': 'creature', 'who': 'enchanted'}
    else:
        return None
    return {**base, 'conditions': [*base.get('conditions', []), cond]} if base is not None else None
