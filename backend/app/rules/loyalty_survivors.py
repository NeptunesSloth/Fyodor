"""CR 101.4 / 611.2b: chosen survivors, per-player counters, and counter-bound restrictions."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'chosen_controllers_put_counters'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    if body.strip() != ('Each player puts a vow counter on a creature they control and sacrifices the rest. '
                        "Each of those creatures can't attack you or planeswalkers you control for as long as it has a vow counter on it."):
        return None
    creatures = selectors.parse('creature')
    assert creatures is not None
    return ([{'do': 'player_chooses', 'who': 'each_player', 'sel': creatures.key(), 'n': 1,
              'label': 'creature to keep', 'as': 'loyalty_choices'},
             {'do': STEP, 'who': 'ref:loyalty_choices', 'kind': 'vow', 'n': 1},
             {'do': 'sacrifice', 'who': 'except:loyalty_choices|' + creatures.key(), 'by': 'controller'},
             {'do': 'until', 'duration': 'while_counter:vow', 'n': 1},
             {'do': 'restrict', 'who': 'ref:loyalty_choices', 'rules': ['cant_attack_player_pw:@you'], 'locked': True}], None, False)


def put(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, replace

    cards = effects._cards(plan, ctx, e['who'])
    if not cards:
        return True
    return replace.put_counters(plan, [(cid, e['kind'], e['n']) for cid in cards], by=ctx['controller'],
                                putters=[plan.state.cards[cid].controller for cid in cards],
                                then=effects._then(ctx, e), ctx=ctx)


PRIMITIVES = {STEP: put}
