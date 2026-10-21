"""Stack target predicates depend on actual entries and exact source incarnations."""
from __future__ import annotations

from typing import Any


def matches(plan: Any, card: Any, extra: str, source: str | None) -> bool:
    if extra == 'random_has_targets':
        from app.rules import copying, stack_interaction

        targeted = stack_interaction.target_entry(plan, card.id)
        return targeted is not None and bool(copying.positions(targeted))
    if extra.startswith('random_artisans_uncontested'):
        from app.rules import card_names, source_shields

        oid = plan.oid(card)
        source_oid = extra.split(':', 1)[1] if ':' in extra else plan.oid(source) if source in plan.state.cards else None
        for sid, other in plan.rules.stack.items():
            if other.source_object is None or other.source_object == source_oid:
                continue
            ability = plan.state.cards.get(sid)
            if ability is None or ability.ability is None:
                continue
            refs = [*other.targets, *(t for group in other.groups for t in group), *(t for slot in other.slots for t in slot)]
            if not any(t.id == card.id and t.object_id == oid for t in refs):
                continue
            ch = source_shields._ch_of(plan, other.source_card, other.source_object)
            if ch is not None and ch.is_creature and 'Goblin Artisans' in card_names.names_of(ch):
                return False
        return True
    return True
