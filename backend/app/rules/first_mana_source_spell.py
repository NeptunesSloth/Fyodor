"""CR 601.2i, 608.2i: the first spell paid with mana from a stated source type."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import CastNote
    from app.rules.plan import Plan

TAGS = {'a Treasure': 'Treasure', 'an artifact': 'Artifact', 'a creature': 'Creature', 'a Desert': 'Desert', 'a Cave': 'Cave'}


def definition(text: str) -> dict[str, Any] | None:
    m = re.fullmatch(r'the first spell you cast each turn that mana from (a Treasure|an artifact|a creature|a Desert|a Cave) was spent to cast has (cascade|storm)', text)
    if m is None:
        return None
    return {'kind': 'static', 'static': 'spell_keyword', 'keyword': m[2], 'count': 1,
            'filter': None, 'from': None, 'first': 'mana_source', 'mana_tag': TAGS[m[1]], 'effects': []}


def eligible(plan: Plan, object_id: str, earlier: list[CastNote], tag: str) -> bool:
    record = plan.rules.payments.get(object_id)
    return bool(record is not None and record.mana_known and any(tag in tags for tags in record.mana_tags)
                and not any(tag in tags for note in earlier for tags in note.mana_tags))
