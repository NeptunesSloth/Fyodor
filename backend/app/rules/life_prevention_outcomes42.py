"""Exact life-lock outcomes and Transcendence pure-state recipe."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STATE_STEP = 'transcendence_state_loss'
STATE_TEXT = 'When you have 20 or more life, you lose the game.'
FLAMES = "~ deals 4 damage to target player or planeswalker. The damage can't be prevented. If that player or that planeswalker's controller would gain life this turn, that player gains no life instead."
NEMESIS = "Whenever ~ is dealt damage, it deals that much damage to any other target. If a player is dealt damage this way, they can't gain life for the rest of the game."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import conditions, events, scripts

    text = scripts.self_text(ability.text, ch.name).replace('this creature', '~')
    if ability.kind == 'triggered' and text == STATE_TEXT:
        condition = conditions.parse('you have 20 or more life', objects=True)
        assert condition is not None
        return {'kind': 'triggered', 'trigger': 'state', 'state': condition, 'effects': [{'do': STATE_STEP}]}
    if ability.kind == 'triggered' and text == 'Whenever you lose life, you gain 2 life for each 1 life you lost.':
        return {'kind': 'triggered', 'trigger': 'event', 'cond': events.parse_condition('you lose life'),
                'effects': [{'do': 'gain_life', 'who': 'you', 'n': {'times': [2, {'event_amount': 1}]}}]}
    if ability.kind == 'triggered' and text == NEMESIS:
        return {'kind': 'triggered', 'trigger': 'event', 'cond': events.parse_condition('~ is dealt damage'),
                'target': {'what': 'any_other'},
                'effects': [{'do': 'damage', 'who': 'target', 'n': {'event_amount': 1}, 'bind_damage_players': 'nemesis_dealt'},
                            {'do': 'cant_gain_life', 'who': 'ref:nemesis_dealt', 'until': 'game'}]}
    return None


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body == FLAMES:
        return [{'do': 'life_prevention_outcome', 'mode': 'flames_start'}], 'player_or_planeswalker', False
    return None


def state_loss(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import immortal_coil_outcomes, win_game

    if immortal_coil_outcomes.mandatory_loop(plan, ctx, step=STATE_STEP, state_text=STATE_TEXT, definition_factory=definition):
        plan.rules.draw_reason = 'Mandatory state-trigger loop (104.4b, 732.4)'
        plan.rules.priority = None
        plan.rules.decision = None
        plan.note('The game is a draw: the mandatory pure-loss state-trigger loop cannot end (104.4b, 732.4)')
        return False
    return win_game.lose_game(plan, ctx, {'who': 'you'})


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, replace

    if e['mode'] == 'flames_start':
        recipients = effects._players(plan, ctx, 'target')
        recipients += [plan.state.cards[c].controller for c in effects._cards(plan, ctx, 'target')]
        context.bind_players(ctx, 'flames_original_player', list(dict.fromkeys(recipients)))
        ctx['effects'][ctx['next']:ctx['next']] = [
            {'do': 'damage', 'who': 'target', 'n': 4, 'unpreventable': True},
            {'do': 'life_prevention_outcome', 'mode': 'flames_finish'}]
        return True
    if e['mode'] == 'flames_finish':
        recipients = context.players(plan, ctx, 'flames_original_player')
        if recipients:
            replace.add_record(plan, event='life', match={'players': recipients}, op={'do': 'set', 'n': 0},
                               controller=ctx['controller'], source=ctx.get('source_object'),
                               source_card=ctx.get('source_card'), label=ctx.get('name') or 'Flames of the Blood Hand')
        return True
    raise ValueError('Unknown life/prevention outcome')


PRIMITIVES = {STATE_STEP: state_loss, 'life_prevention_outcome': run}
