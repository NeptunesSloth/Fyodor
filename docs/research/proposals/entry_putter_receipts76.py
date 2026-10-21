"""Committed entry putters remain distinct from permanent controllers."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan


TEXTS = {
    "Whenever a player puts a Forest onto the battlefield, ~ deals 3 damage to that player unless they put a -1/-1 counter on a creature they control.": 'Forest',
    "Whenever a player puts a Swamp onto the battlefield, ~ deals 3 damage to that player unless the player puts a -1/-1 counter on a creature they control.": 'Swamp',
}


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import optional_payment, scripts

    subtype = TEXTS.get(scripts.self_text(ability.text, ch.name))
    if subtype is None:
        return None
    native = scripts.define(replace(ability, text=f'Whenever a {subtype} enters, ~ deals 3 damage to that player.'), ch)
    cost = optional_payment.cost_text('put a -1/-1 counter on a creature you control')
    assert native is not None and cost is not None
    return {**native, 'cond': {**native['cond'], 'event': 'put_battlefield'}, 'effects': [
        {'do': 'optional_payment', 'who': 'event_player', 'cost': cost, 'bind': 'entry76_paid'},
        {'do': 'only_if', 'cond': {'succeeded': 'entry76_paid', 'negate': True}, 'skip': 1},
        *native['effects']]}


def return_putter(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], cid: str) -> str:
    return plan.state.cards[cid].owner if e.get('entry_putter') == 'owner' else str(ctx['controller'])


def owner_returns(body: str, it: str | None, event_player: bool) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Retain the actor of the existing 'each player returns all' native rewrite."""
    from app.rules import scripts

    matches = list(scripts._EACH_RETURNS.finditer(body))
    if len(matches) != 1 or matches[0]['d'] != 'the battlefield':
        return None
    rewritten = scripts._split_tails(body, event_player)
    parsed = scripts.parse_effects(rewritten, it, event_player=event_player)
    if parsed is None:
        return None
    effects, target, optional = parsed
    returns = [i for i, e in enumerate(effects) if e.get('do') == 'return_card' and e.get('to') == 'battlefield']
    if len(returns) != 1:
        return None
    index = returns[0]
    return ([{**e, 'entry_putter': 'owner'} if i == index else e for i, e in enumerate(effects)], target, optional)
