"""Control of a spell changes its controller, not its owner, choices, identity or stack position."""
from __future__ import annotations

import re
from typing import Any

from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    m = re.fullmatch(r'Gain control of target (?P<non>noncreature )?spell\. You may choose new targets for it\.', body, re.IGNORECASE)
    if m:
        return [{'do': 'gain_control_spell', 'who': 'target'}, {'do': 'choose_new_targets', 'who': 'target'}], selectors.Selector(
            zones=('stack',), not_types=('Creature',) if m['non'] else ()).key(), False
    if re.fullmatch(r'Choose target spell, then flip a coin\. If you win the flip, gain control of that spell and you may choose new targets for it\. If you lose the flip, counter that spell\.', body, re.IGNORECASE):
        return [{'do': 'choose_targets', 'who': 'target'}, {'do': 'coin_flip'},
                {'do': 'only_if', 'cond': {'coin': 'win'}, 'skip': 2},
                {'do': 'gain_control_spell', 'who': 'target'}, {'do': 'choose_new_targets', 'who': 'target'},
                {'do': 'only_if', 'cond': {'coin': 'lose'}, 'skip': 1}, {'do': 'counter', 'who': 'target'}], selectors.Selector(zones=('stack',)).key(), False
    return None


def gain_control(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.effects import _stack_targets

    for sid in _stack_targets(plan, ctx, e):
        spell = plan.state.cards[sid]
        if spell.ability is None:
            plan.do({'type': 'set_controller', 'card_ids': [sid], 'player': ctx['controller']}, actor=ctx['controller'])
    return True
