"""A successful control exchange followed by energy and an optional retention payment."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_FORM = re.compile(
    r'(?P<exchange>[Ee]xchange control of ~ and target creature an opponent controls)\. '
    r'If you do, you get (?P<energy>(?:\{E\})+), then sacrifice that creature unless you pay '
    r'an amount of \{E\} equal to its mana value\.')


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    m = _FORM.fullmatch(body.strip())
    if m is None:
        return None
    from app.rules import scripts

    native = scripts.parse_effects(m['exchange'] + '.')
    if native is None or len(native[0]) != 1 or native[0][0]['do'] != 'exchange_control':
        return None
    return [{'do': 'exchange_energy', 'exchange': native[0][0], 'energy': m['energy'].count('{E}')}], native[1], False


def exchange(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    native = e['exchange']
    first_ids, second_ids = effects._cards(plan, ctx, native['who']), effects._cards(plan, ctx, native['with'])
    if len(first_ids) != 1 or len(second_ids) != 1 or first_ids == second_ids:
        return True
    first, second = plan.state.cards[first_ids[0]], plan.state.cards[second_ids[0]]
    ids = first.id, second.id
    objects = plan.oid(first), plan.oid(second)
    controllers = first.controller, second.controller
    if controllers[0] == controllers[1]:
        return True
    effects.exchange_control(plan, ctx, native)
    live = [plan.state.cards.get(cid) for cid in ids]
    if any(card is None or plan.oid(card) != oid for card, oid in zip(live, objects, strict=True)):
        return True
    if [card.controller for card in live if card is not None] != [controllers[1], controllers[0]]:
        return True
    at = int(ctx.get('next') or 0)
    bind = f'exchange_energy_{at}'
    rest = [{'do': 'player_counter', 'who': 'you', 'counter': 'energy', 'n': e['energy']},
            {'do': 'optional_payment', 'who': 'you', 'cost': '', 'energy_n': {'mana_value': native['with']}, 'bind': bind},
            {'do': 'only_if', 'cond': {'succeeded': bind, 'negate': True}, 'skip': 1},
            {'do': 'sacrifice', 'who': native['with']}]
    ctx['effects'] = [*ctx['effects'][:at], *rest, *ctx['effects'][at:]]
    return True


PRIMITIVES = {'exchange_energy': exchange}
