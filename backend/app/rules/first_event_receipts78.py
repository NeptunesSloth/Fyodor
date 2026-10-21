"""First actions are recorded even when no permanent watches; old unknown history is explicit."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXTS = {
    'Whenever you investigate for the first time each turn, investigate an additional time.': 'investigate',
    'Whenever you cycle another card for the first time each turn, create a 1/1 white Human Soldier creature token.': 'cycle',
    'Whenever one or more land cards are put into your graveyard from anywhere for the first time each turn, create a 1/1 green Insect creature token.': 'land_graveyard',
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text not in TEXTS:
        return None
    kind = TEXTS[ability.text]
    base = ability.text.replace(' for the first time each turn', '')
    if kind == 'investigate':
        base = 'Whenever you gain life, investigate.'
    native = scripts.define(replace(ability, text=base), ch)
    if native is None:
        return None
    condition = {**native['cond'], 'first_event78': kind, 'first_event_index78': ability.index}
    if kind == 'investigate':
        condition['event'] = 'investigate'
    return {**native, 'cond': condition}


def annotate(plan: Any, facts: list[Any], batch: int, first_batches: dict[str, tuple[int, bool | None]]) -> None:
    turn = plan.state.turn.number
    for kind, _card, ch, player, info in facts:
        mode = kind if kind in {'cycle', 'investigate'} else (
            'land_graveyard' if kind == 'to_graveyard' and ch is not None and 'Land' in ch.types else None)
        if mode is None or not isinstance(player, str):
            continue
        key = 'first78:' + mode + ':' + player
        if mode == 'land_graveyard' and key in first_batches and first_batches[key][0] == batch:
            first = first_batches[key][1]
        elif plan.rules.once_per_turn.get(key) == turn:
            first = False
        else:
            first = True if plan.rules.first_event_history_turn78 == turn else None
            plan.rules.once_per_turn[key] = turn
            first_batches[key] = (batch, first)
        info['first_event78'] = first


def matches(plan: Any, condition: dict[str, Any], watcher: Any, fact: Any, source_oid: str | None = None) -> bool:
    from app.game.rules_state import FirstEventHistoryNotice78
    from app.rules import triggers

    native = {k: v for k, v in condition.items() if k not in {'first_event78', 'first_event_index78'}}
    if not triggers._cond_matches(plan, native, watcher, fact, source_oid=source_oid):
        return False
    result = fact[4].get('first_event78')
    if result is not None:
        return result is True
    # All ordinary subject/event/actor conditions have already matched. Do not fabricate a trigger.
    oid, index, turn = source_oid or plan.oid(watcher), condition['first_event_index78'], plan.state.turn.number
    if not any(n.source_object == oid and n.ability == index and n.controller == watcher.controller and n.turn == turn
               for n in plan.rules.first_event_notices78):
        plan.rules.first_event_notices78.append(FirstEventHistoryNotice78(source_object=oid, ability=index,
            controller=watcher.controller, turn=turn, name=watcher.name[:500]))
    return False


def investigate(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, this_way

    # Current canonical investigate recipes have no bound token cohort (151-card scan).
    if e.get('as') or e.get('more'):
        from app.game.errors import ActionError

        raise ActionError('Bound investigation receipts require manual resolution.')
    n = max(0, effects._amount(plan, ctx, e['n']))
    each = this_way.by_controller(plan, ctx, e['per_controller']) if e.get('per_controller') else {
        pid: 1 for pid in effects._players(plan, ctx, e['who'])}
    steps = []
    base = {k: v for k, v in e.items() if k not in {'investigate78', 'per_controller'}}
    for pid in plan.apnap():
        if pid not in each:
            continue
        for _ in range(n * each[pid]):
            steps += [{**base, 'who': 'player:' + pid, 'n': 1}, {'do': 'investigate_complete78', 'player': pid}]
    ctx['effects'][ctx['next']:ctx['next']] = steps
    return True


def complete(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import emit

    emit(plan.state, 'investigated', player=e['player'], actor=e['player'], amount=1)
    return True


def ask_pending(plan: Any) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if plan.rules.decision is not None:
        return False
    plan.rules.first_event_notices78 = [n for n in plan.rules.first_event_notices78 if n.turn == plan.state.turn.number]
    for player in plan.apnap():
        notices = [n for n in plan.rules.first_event_notices78 if n.controller == player and not n.notified]
        if not notices:
            continue
        for notice in notices:
            notice.notified = True
        names = ', '.join(dict.fromkeys(n.name for n in notices))[:150]
        decide(plan, player=player, kind='manual_resolution',
               prompt=f'Older save: earlier actions this turn are unknown for {names}. Resolve any applicable first-time triggers by hand, then press Done.',
               options=[DecisionOption(id='done', label='Done')],
               resume={'step': 'first_event_legacy_done78', 'priority': plan.rules.priority})
        return True
    return False


def legacy_done(plan: Any, decision: Any, chosen: list[str]) -> None:
    old = decision.resume.get('priority')
    plan.rules.priority = old if old in plan.live() else None



def recipes_ok(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get('investigate78') and (value.get('as') or value.get('more')):
            return False
        return all(recipes_ok(v) for v in value.values())
    return not isinstance(value, list) or all(recipes_ok(v) for v in value)



def note_events(plan: Any, events: list[Any], log: Any) -> None:
    from app.game.rules_state import TurnFact

    for event in events:
        if event.manual or event.turn != plan.state.turn.number or event.kind not in {'investigated', 'cycled'} or not event.player:
            continue
        log.facts.append(TurnFact(kind='investigate' if event.kind == 'investigated' else 'cycle',
                                 player=event.player, object_id=event.object_id, amount=1, batch=event.batch))
