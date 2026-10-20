"""Unregistered bounded layer-six loss of the exact quoted self-prevention ability."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import ContinuousEffect
    from app.rules.plan import Plan

LOSS = 'prevent_all_damage_to_self'
ABILITY = 'Prevent all damage that would be dealt to ~.'
BODY = 'Until end of turn, ~ loses "' + ABILITY + '"'
STEP = 'lose_quoted_prevention47'


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    if body.strip() not in (BODY, BODY + ' Any player may activate this ability.'):
        return None
    return [{'do': STEP}], None, False


def matches(text: str, name: str) -> bool:
    from app.rules import granted, scripts

    normalized = scripts.self_text(text.strip(), name).replace('this creature', '~').replace('this permanent', '~')
    return granted.with_final_stop(normalized) == ABILITY


def lost(text: str, name: str, granted: tuple[int, int, int], effects: list[ContinuousEffect]) -> bool:
    if not matches(text, name):
        return False
    return any(e.layer == '6' and getattr(e, 'lose_quoted_ability', None) == LOSS
               and (e.object_seq, 1, e.timestamp) >= granted for e in effects)


def run(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import effects, layers

    for cid in effects._cards(plan, ctx, 'self'):
        card = plan.state.cards[cid]
        if not card.zone.endswith(':battlefield') or not plan.in_game(card):
            continue
        layers.add_effect(plan, affected=[plan.oid(cid)], layer='6', source=ctx.get('source_object'),
                          source_card=ctx.get('source_card'), controller=ctx['controller'],
                          duration='end_of_turn', label='loses its quoted self-prevention ability',
                          lose_quoted_ability=LOSS)
    return True


PRIMITIVES = {STEP: run}
