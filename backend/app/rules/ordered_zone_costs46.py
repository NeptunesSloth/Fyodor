"""Native exact hand-to-library activation cost and Hidden Retreat prevention."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.costs import CostComponent
    from app.rules.plan import Plan

HAND_TO_TOP = 'HAND_TO_TOP'
HAND_TEXT = 'Put a card from your hand on top of your library'
RETREAT = 'Prevent all damage that would be dealt by target instant or sorcery spell this turn.'


def component(part: str) -> CostComponent | None:
    from app.rules import costs, selectors

    if part != HAND_TEXT:
        return None
    key = selectors.Selector(card=True, zones=('hand',), zone_owner='you').key()
    return costs.CostComponent(HAND_TO_TOP, selector=key, text=part)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip() != RETREAT:
        return None
    return ([{'do': 'source_shield', 'props': {}, 'once': False, 'src': 'target', 'to': None}],
            'instant_or_sorcery_spell', False)


def pay_hand_to_top(plan: Plan, ids: list[str], player: str) -> None:
    """Used only from actual native cost settlement after its chosen-card revalidation."""
    if ids:
        plan.do({'type': 'move', 'card_ids': list(ids), 'to': {'player': player, 'zone': 'library'},
                 'position': 'top'}, actor=player)
