"""Exact Coil outcomes: genuine state trigger and isolated pure-loss loop proof."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'coil_state_loss'
STATE_TEXT = 'When there are no cards in your graveyard, you lose the game.'
PREVENT_TEXT = 'If damage would be dealt to you, prevent that damage. Exile a card from your graveyard for each 1 damage prevented this way.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import conditions, selectors

    if ability.kind == 'static' and ability.text == PREVENT_TEXT:
        selector = selectors.parse('cards in your graveyard')
        assert selector is not None
        return {'kind': 'static', 'static': 'replace', 'event': 'damage', 'match': {'to': {'players': 'you'}},
                'op': {'do': 'prevent_all', 'prevention': True, 'rider': {'aggregation': 'batch', 'effects': [
                    {'do': 'return_choice', 'sel': selector.key(), 'n': {'ref_amount': 'prevented'}, 'to': 'exile'}]}},
                'effects': []}
    if ability.kind == 'triggered' and ability.text == STATE_TEXT:
        condition = conditions.parse('there are no cards in your graveyard', objects=True)
        assert condition is not None
        return {'kind': 'triggered', 'trigger': 'state', 'state': condition, 'effects': [{'do': STEP}]}
    return None


def _key(effects: list[dict[str, Any]]) -> str | None:
    return str(effects[0]['key']) if effects and effects[0].get('do') == 'state_trigger' else None


def mandatory_loop(plan: Plan, ctx: dict[str, Any], *, step: str = STEP, state_text: str = STATE_TEXT,
                   definition_factory: Callable[[Any, Any], dict[str, Any] | None] = definition) -> bool:
    """Prove a fresh identical mandatory trigger follows this blocked pure loss.

    Normal priority has already occurred before this actual resolution. An
    external action is never forced to escape the loop (732.5).
    """
    from app.rules import conditions, game_result, scripts, win_game

    body = ctx.get('effects') or []
    key = _key(body)
    if ctx.get('kind') != 'trigger' or key is None or len(body) != 2 or body[1] != {'do': step}:
        return False
    current = plan.rules.stack.get(ctx.get('stack_id') or '')
    if current is None or current.optional or current.effects != body:
        return False
    controller = ctx['controller']
    if controller not in plan.live() or not game_result.cannot_lose(plan, controller) or win_game._unread_blocker(plan, 'lose'):
        return False
    source = plan.state.cards.get(ctx.get('source_card') or '')
    if (source is None or not source.zone.endswith(':battlefield') or not plan.in_game(source)
            or plan.oid(source) != ctx.get('source_object') or source.controller != controller):
        return False
    oid, _, index = key.rpartition(':')
    if oid != plan.oid(source) or not index.isdecimal():
        return False
    ch = plan.ch(source)
    ability = next((a for a in ch.abilities if a.index == int(index) and a.text == state_text), None)
    if ability is None:
        return False
    actual = scripts.definitions(ch).get(int(index))
    expected = definition_factory(ability, ch)
    if actual != expected or actual is None or not conditions.holds(plan, ctx, actual['state']):
        return False
    # A copied instance above an intervening object cannot prove what happens
    # after the original. Wait for the last actual instance of this state key.
    if any(_key(t.ability.get('effects') or []) == key for t in plan.rules.pending_triggers):
        return False
    return not any(sid != ctx['stack_id'] and _key(entry.effects) == key for sid, entry in plan.rules.stack.items())


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import win_game

    if mandatory_loop(plan, ctx):
        plan.rules.draw_reason = 'Mandatory state-trigger loop (104.4b, 732.4)'
        plan.rules.priority = None
        plan.rules.decision = None
        plan.note('The game is a draw: the mandatory loss/prevention state-trigger loop cannot end (104.4b, 732.4)')
        return False
    # The trigger has no intervening "if": a later nonempty graveyard or a
    # departed source does not stop the already-triggered loss instruction.
    return win_game.lose_game(plan, ctx, {'who': 'you'})


PRIMITIVES = {STEP: run}
