"""Pure prevention receipts are published only when their damage batch commits."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan
    from app.rules.replace import Candidate


def receipt(candidate: Candidate, event: dict[str, Any], amount: int) -> dict[str, Any]:
    key = [event.get('_damage_lineage'), candidate.id, event['target'], event.get('applied') or []]
    return {'id': json.dumps(key, separators=(',', ':')), 'candidate': candidate.id, 'amount': amount,
            'source_card': event.get('source_card'), 'source_oid': event.get('source_oid'),
            'source': dict(event.get('src') or {}), 'target': event['target'],
            'target_oid': event.get('target_oid'), 'combat': bool(event.get('combat')),
            'controller': candidate.controller, 'effect_card': candidate.source_card,
            'effect_object': candidate.source_oid}


def collect(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # A later redirect splits an event but must not duplicate its earlier prevention.
    return list({r['id']: r for event in events for r in event.get('prevention_receipts') or []}.values())


def commit(plan: Plan, receipts: list[dict[str, Any]]) -> None:
    from app.game.rules_state import emit

    for row in receipts:
        target = row['target']
        emit(plan.state, 'damage_prevented', amount=row['amount'], source=row.get('source_oid'),
             player=target if target in plan.state.players else None,
             card=target if target in plan.state.cards else None, object_id=row.get('target_oid'),
             combat=row['combat'], actor=row['controller'], prevention=row)
