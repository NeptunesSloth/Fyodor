"""CR 301.5, 613.1d: Equipment that turns its attached permanent into a creature.

Attachment legality considers the continuous type change that would immediately
apply to its host. Probes are read-only and never emit an attachment event.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan


def definition(body: str) -> dict[str, Any] | None:
    if body != "Equipped permanent isn't a planeswalker and is a creature in addition to its other types":
        return None
    return {'kind': 'static', 'static': 'grant', 'effects': [], 'who': 'attached', 'attached_kind': 'permanent',
            'conditions': [], 'p': 0, 't': 0, 'base': None, 'keywords': [], 'grants': [], 'rules': [],
            'layer4': {'remove_types': ['Planeswalker'], 'add_types': ['Creature']}}


def makes_host_creature(plan: Plan, source: CardInstance, host: CardInstance) -> bool:
    from app.rules import scripts
    from app.rules.plan import Plan

    # Ordinary Equipment need no hypothetical table derivation.
    if not any(d.get('static') == 'grant' and d.get('who') == 'attached'
               and 'Creature' in (d.get('layer4') or {}).get('add_types', [])
               for d in scripts.definitions(plan.ch(source)).values()):
        return False
    probe = plan.state.model_copy(update={'cards': {**plan.state.cards,
                source.id: source.model_copy(update={'attached_to': host.id, 'attached_player': None})}})
    return Plan.view(probe, plan.actor, plan.info).ch(probe.cards[host.id]).is_creature
