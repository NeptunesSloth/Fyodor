"""Protection's damage prevention participates in native replacement ordering."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan
    from app.rules.replace import Candidate


def candidates(plan: Plan) -> list[Candidate]:
    from app.rules.replace import Candidate

    targets: list[tuple[str, str | None, str, str]] = [(pid, None, pid, f'{plan.name(pid)}: protection') for pid in plan.live()]
    targets += [(card.id, plan.oid(card), card.controller, f'{plan.ch(card).name}: protection')
                for card in plan.state.cards.values()
                if card.zone.endswith(':battlefield') and plan.in_game(card)
                and 'protection' in plan.ch(card).keywords]
    return [Candidate(id=f'protection:{oid or target}', event='damage', match={},
                      op={'do': 'prevent_all', 'prevention': True, 'protection_target': target,
                          'protection_object': oid}, controller=controller,
                      source_card=target if oid else None, source_oid=oid,
                      seq=(0, 4, i), label=label)
            for i, (target, oid, controller, label) in enumerate(targets)]


def applies(plan: Plan, candidate: Candidate, event: dict[str, Any]) -> bool:
    from app.rules import player_shields, protection, source_shields, targets

    target = candidate.op['protection_target']
    if event['target'] != target:
        return False
    oid = candidate.op.get('protection_object')
    if oid and (target not in plan.state.cards or plan.oid(target) != oid):
        return False
    src = event.get('src') or {}
    source = targets.source_of(plan, event.get('source_card'), bool(src.get('spell')),
                               object_id=event.get('source_oid'))
    protected = (player_shields.protected_from(plan, target, source) is not None
                 if target in plan.state.players else source is not None and
                 protection.protected_from(plan.ch(plan.state.cards[target]), source))
    return bool(protected and source_shields.protection_applies(plan, event))
