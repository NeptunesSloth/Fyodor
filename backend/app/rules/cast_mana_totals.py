"""CR 202.3e, 601.2i, 608.2h: sum mana values from this turn's cast snapshots."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(phrase: str) -> dict[str, Any] | None:
    from app.rules import conditions

    m = re.fullmatch(r"the total mana value of (?P<other>other )?(?P<kind>.*?)spells you(?:'ve| have) cast this turn", phrase)
    if m is None:
        return None
    kind = re.sub(r'^(instant|sorcery) and (instant|sorcery) ', r'\1 or \2 ', m['kind'])
    key = conditions._history_sel(kind + 'spells', 'stack')
    return None if key is None else {'cast_mana_total': key, 'other': bool(m['other'])}


def evaluate(plan: Plan, ctx: dict[str, Any], value: dict[str, Any]) -> int:
    from app.rules import history, selectors

    sel = selectors.from_key(value['cast_mana_total'])
    source = history._source_object(plan, ctx) if value.get('other') else None
    return sum(int(note.mv) for note in history.log_for(plan).casts
               if note.player == ctx['controller'] and (source is None or source not in (note.object_id, note.became))
               and history.note_matches(sel, note.types, note.subtypes, note.supertypes, note.colors, note.mv, x_cost=note.x_cost))
