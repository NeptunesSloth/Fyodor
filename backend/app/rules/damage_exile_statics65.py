"""Static exile replacements consult actual damage to this turn's original objects."""
from __future__ import annotations

from typing import Any

TEXTS = {
    'If a creature dealt damage by enchanted creature this turn would die, exile it instead.': 'attached',
    'If a creature dealt damage this turn by a source you controlled would die, exile it instead.': 'controlled',
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    scope = TEXTS.get(scripts.self_text(ability.text, ch.name))
    if scope is None:
        return None
    return {'kind': 'static', 'static': 'exile_instead', 'from': 'battlefield',
            'who': selectors.Selector(types=('Creature',)).key(), 'damaged_source_scope': scope}


def matches(plan: Any, source: Any, creature: Any, scope: str) -> bool:
    from app.rules import history

    if scope not in ('attached', 'controlled'):
        return False
    host = plan.state.cards.get(source.attached_to or '') if scope == 'attached' else None
    if scope == 'attached' and (host is None or not host.zone.endswith(':battlefield')):
        return False
    oid = plan.oid(creature)
    host_oid = plan.oid(host) if host is not None else None
    return any(f.kind == 'damaged' and f.amount > 0 and f.object_id == oid
               and ((f.source == host_oid) if scope == 'attached' else f.source_controller == source.controller)
               for f in history.log_for(plan).facts)
