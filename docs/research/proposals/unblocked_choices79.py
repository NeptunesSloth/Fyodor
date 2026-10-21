"""Unblocked riders use original attacker identity and committed native instructions."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

MASTER = "Whenever this creature attacks a player and isn't blocked, that player's life total becomes 1. This creature assigns no combat damage this combat."
BONE = "Whenever this creature attacks and isn't blocked, you may put the top creature card of defending player's graveyard onto the battlefield under your control. If you do, this creature assigns no combat damage this turn."
SPY = "Whenever this creature attacks and isn't blocked, you may have defending player play with their hand revealed for as long as this creature remains on the battlefield. If you do, this creature assigns no combat damage this turn."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text not in {MASTER, BONE, SPY}:
        return None
    prefix = ability.text.split(', ', 1)[0]
    native = scripts.define(replace(ability, text=prefix + ', draw a card.'), ch)
    if native is None:
        return None
    none = {'do': 'restrict', 'who': 'self', 'rules': ['assign_none']}
    if ability.text == MASTER:
        steps = [{'do': 'set_life', 'who': 'defending_player', 'n': 1}, {**none, 'duration': 'end_of_combat'}]
    else:
        steps = [{'do': 'may_rest'}, {'do': 'bone_entry79' if ability.text == BONE else 'spy_reveal79'}]
    return {**native, 'effects': steps}


def bone_entry(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    defenders = effects._players(plan, ctx, 'defending_player')
    if len(defenders) != 1:
        return True
    selected = next((cid for cid in reversed(plan.state.zones.get(defenders[0] + ':graveyard', []))
                     if not plan.state.cards[cid].is_token and plan.ch(plan.state.cards[cid]).is_creature), None)
    if selected is not None:
        context.bind_objects(plan, ctx, 'bone_top79', [selected])
        ctx['effects'][ctx['next']:ctx['next']] = [
            {'do': 'return_card', 'who': 'ref:bone_top79', 'to': 'battlefield', 'tapped': False, 'under': 'you', 'entry_receipt56': 'bone_entered79'},
            {'do': 'bone_finish79'}]
    return True


def spy_reveal(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import SourceHandReveal79
    from app.rules import delayed, effects

    if delayed._source_ok(plan, 'source_on_battlefield', ctx.get('source_card'), ctx.get('source_object'), ctx['controller']):
        for player in effects._players(plan, ctx, 'defending_player'):
            plan.rules.source_hand_reveals79.append(SourceHandReveal79(
                player=player, source_card=ctx['source_card'], source_object=ctx['source_object']))
    ctx['effects'][ctx['next']:ctx['next']] = [{'do': 'restrict', 'who': 'self', 'rules': ['assign_none']}]
    return True


def bone_finish(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, entry_receipt56

    entry_receipt56.finish(plan, ctx, 'bone_entered79')
    if context.succeeded(ctx, 'bone_entered79:paid'):
        return effects.restrict(plan, ctx, {'who': 'self', 'rules': ['assign_none']})
    return True
