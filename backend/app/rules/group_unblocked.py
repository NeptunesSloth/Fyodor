"""CR 510.1c, 611.3a: group permissions change assignment without granting abilities.

The existing combat chooser asks separately for each eligible blocked attacker.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import selectors

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

STATIC = 'group_assign_unblocked'


def definition(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text == "Enchanted creature's controller may have it assign its combat damage as though it weren't blocked.":
        return {'kind': 'static', 'static': STATIC, 'who': 'attached', 'source_attacking': False, 'effects': []}
    m = re.fullmatch(r"(?P<attacking>As long as (?:~|this creature) is attacking, )?[Ff]or each (?P<what>.+?), "
                     r"you may have that creature assign its combat damage as though it weren't blocked\.", text)
    if m is None:
        return None
    sel = selectors.parse(m['what'])
    if sel is None or sel.player is not None or sel.card or sel.zones != ('battlefield',) or sel.types != ('Creature',) or sel.controller != 'you':
        return None
    return {'kind': 'static', 'static': STATIC, 'who': sel.key(), 'source_attacking': bool(m['attacking']), 'effects': []}


def allows(plan: Plan, creature: CardInstance, ch: Characteristics) -> bool:
    from app.rules import permissions, scripts

    if 'assign_unblocked' in scripts.statics(ch):
        return True
    if 'assign_unblocked110m' in ch.imposed:  # -- (wave 110M) -- Gurzigost: "this turn", one creature
        return True
    if plan.rules.assign_unblocked_turn.get(creature.controller) == plan.state.turn.number:  # -- wave 110A -- Predatory Focus
        return True
    for source, _, d in permissions._table_statics(plan.state, plan.info, {STATIC}):
        if d['source_attacking'] and not source.is_attacking:
            continue
        if d['who'] == 'attached':
            if source.attached_to == creature.id:
                return True
        elif selectors.matches(plan, selectors.from_key(d['who']), creature, ch, source.controller, source.id):
            return True
    return False
