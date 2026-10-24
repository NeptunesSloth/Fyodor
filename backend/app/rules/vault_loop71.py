"""A private repeated five-card look and retained-final-packet shuffle."""
from __future__ import annotations

from typing import Any

from app.rules.plan import Plan

_TEXT = "Look at the top five cards of your library. As many times as you choose, you may pay 1 life, put those cards on the bottom of your library in any order, then look at the top five cards of your library. Then shuffle and put the last cards you looked at this way on top in any order."


def parse(text: str) -> Any:
    if text.strip().casefold() != _TEXT.casefold():
        return None
    return ([{'do': 'look_top', 'n': 5, 'player': 'you', 'reveal': False, 'exact_look': True},
             {'do': 'optional_payment', 'who': 'you', 'cost': 'Pay 1 life', 'bind': 'vault_pay71'},
             {'do': 'only_if', 'cond': {'succeeded': 'vault_pay71'}, 'skip': 2},
             {'do': 'rest_looked', 'to': 'bottom_any'}, {'do': 'vault_again71'},
             {'do': 'vault_shuffle71'}, {'do': 'rest_looked', 'to': 'top_any'}], None, False)


def again(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    ctx['next'] -= 5
    return True


def shuffle(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    owner, cards = effects._looked(plan, ctx)
    saved = plan.shuffle_retained
    plan.shuffle_retained = tuple(ref for cid in cards if (ref := context.ref_of(plan, cid)) is not None)
    try:
        plan.do({'type': 'shuffle', 'player': owner, 'zone': 'library'}, actor=ctx['controller'])
    finally:
        plan.shuffle_retained = saved
    return True


PRIMITIVES = {'vault_again71': again, 'vault_shuffle71': shuffle}
