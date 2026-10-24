"""Literal host upkeep grants retain native original-payer resolution semantics."""
from __future__ import annotations

from typing import Any

from app.rules.plan import Plan

MUSIC_QUOTE = 'At the beginning of your upkeep, destroy this creature unless you pay {1} for each music counter on it.'
MUSIC = 'Put a music counter on target creature. If it doesn\'t have "At the beginning of your upkeep, destroy this creature unless you pay {1} for each music counter on it," it gains that ability.'


def normalized(text: str) -> str:
    return text.strip().lower().replace('this creature', '~').replace('this permanent', '~')


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = normalized(body)
    if text == 'destroy ~ unless you pay {1} for each music counter on it.':
        return scripts.parse_effects('Destroy ~ unless you pay {1} for each music counter on ~.')
    if text == 'sacrifice ~ unless you pay its mana cost.':
        return ([{'do': 'upkeep_mana91'}], None, False)
    if text == normalized(MUSIC):
        base = scripts.parse_effects('Put a music counter on target creature.')
        return ([*base[0], {'do': 'music_grant91'}], base[1], False) if base is not None else None
    return None


def music_grant(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, granted, scripts

    for cid in effects._cards(plan, ctx, 'target'):
        ch = plan.ch(plan.state.cards[cid])
        expected = normalized(MUSIC_QUOTE).rstrip('.,;')
        if any(normalized(scripts.self_text(a.text, ch.name)).rstrip('.,;') == expected for a in ch.abilities):
            return True
        quote = granted.quote(MUSIC_QUOTE)
        assert quote is not None
        return effects.grant(plan, ctx, {'who': 'target', 'abilities': [quote], 'duration': 'permanent'})
    return True


def mana_upkeep(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import targets

    ch = targets.source_of(plan, ctx.get('source_card'), object_id=ctx.get('source_object'))
    raw = ch.mana_cost if ch is not None else None
    if not raw:
        ctx['effects'][ctx['next']:ctx['next']] = [{'do': 'sacrifice', 'who': 'self'}]
        return True
    cost = raw.replace('{X}', '') or '{0}'
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do': 'optional_payment', 'who': 'you', 'cost': cost, 'bind': 'upkeep91', 'cost_has_x': '{X}' in raw, 'decline_id': 'sacrifice'},
        {'do': 'only_if', 'cond': {'succeeded': 'upkeep91', 'negate': True}, 'skip': 1},
        {'do': 'sacrifice', 'who': 'self'}]
    return True


PRIMITIVES = {'music_grant91': music_grant, 'upkeep_mana91': mana_upkeep}
