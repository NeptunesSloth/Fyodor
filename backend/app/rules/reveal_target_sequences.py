"""APNAP target groups whose revealed information is consumed sequentially."""
from __future__ import annotations

from typing import Any

from app.game.actions import MAX_TARGETS
from app.game.rules_state import Decision, DecisionOption
from app.rules import context, selectors
from app.rules.plan import Plan, decide


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().rstrip('.')
    text = text[:1].upper() + text[1:]
    if text == "Choose any number of target players or planeswalkers. For each of them, reveal cards from the top of your library until you reveal a nonland card, ~ deals damage equal to that card's mana value to that player or planeswalker, then you put the revealed cards on the bottom of your library in any order":
        return [{'do': 'reveal_target_groups'}], [{'what': 'player_or_planeswalker', 'min': 0, 'max': MAX_TARGETS}], False
    return None


def insert(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    ctx['effects'][ctx['next']:ctx['next']] = steps


def groups(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    pending = e.get('groups')
    if pending is None:
        order = plan.state.turn_order()
        active = plan.state.turn.active_player
        at = order.index(active)
        order = order[at:] + order[:at]
        by_player: dict[str, list[dict[str, Any]]] = {p: [] for p in order}
        for target in effects.target_refs(ctx, 'target'):
            cid = target['id']
            player = cid if cid in plan.state.players else plan.state.cards[cid].controller
            by_player[player].append(target)
        pending = [by_player[p] for p in order if by_player[p]]
    if not pending:
        return True
    first, rest = pending[0], pending[1:]
    if len(first) <= 1:
        queue_group(ctx, first, rest)
        return True
    decide(plan, player=ctx['controller'], kind='order', prompt='Order these targets',
           options=[DecisionOption(id=t['id'], label=plan.name(t['id']) if t['id'] in plan.state.players else plan.ch(plan.state.cards[t['id']]).name,
                                   card_id=t['id'] if t['id'] in plan.state.cards else None) for t in first],
           min_choices=len(first), max_choices=len(first),
           resume={'step': 'reveal_target_order', 'ctx': ctx, 'group': first, 'rest': rest})
    return False


def queue_group(ctx: dict[str, Any], ordered: list[dict[str, Any]], rest: list[Any]) -> None:
    insert(ctx, [*[{'do': 'reveal_target_one', 'target': t} for t in ordered],
                 {'do': 'reveal_target_groups', 'groups': rest}])


def resume_order(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules import effects

    if d.resume is None:
        raise ValueError('A target order requires its saved continuation')
    saved = d.resume
    by_id = {t['id']: t for t in saved['group']}
    queue_group(saved['ctx'], [by_id[c] for c in chosen], saved['rest'])
    effects.continue_effects(plan, saved['ctx'])


def one(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import reveal_outcomes

    until = selectors.Selector(zones=(), card=True, not_types=('Land',)).key()
    if not reveal_outcomes.reveal_outcome_top(plan, ctx, {'do': 'reveal_outcome_top', 'n': 0, 'player': 'you', 'until': until, 'reveal': True, 'exact_look': True}):
        return False
    target = e['target']
    key = f'reveal_recipient_{ctx["next"]}'
    if target['id'] in plan.state.players:
        context.bind_players(ctx, key, [target['id']])
    else:
        cid = target['id']
        card = plan.state.cards.get(cid)
        context.bind_objects(plan, ctx, key, [cid] if card is not None and plan.oid(card) == target.get('object_id') else [])
    found = ctx.get('found')
    value = int(plan.ch(plan.state.cards[found]).mana_value) if isinstance(found, str) and found in (ctx.get('looked') or []) else 0
    insert(ctx, [{'do': 'damage', 'who': 'ref:' + key, 'n': value}, {'do': 'rest_looked', 'to': 'bottom_any'}])
    return True


PRIMITIVES = {'reveal_target_groups': groups, 'reveal_target_one': one}
RESUME = {'reveal_target_order': resume_order}
