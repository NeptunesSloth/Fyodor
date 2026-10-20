"""Restore authoritative combat recipient scope and notify about legacy ambiguity."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

FIELD = 'combat_recipient'


def _without_scope(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_scope(v) for k, v in value.items() if k != FIELD}
    if isinstance(value, list):
        return [_without_scope(v) for v in value]
    return value


def _scope_from_text(text: str, saved: dict[str, Any]) -> str | None:
    from app.rules import events, watches

    parsed = events.parse_condition(text)
    if parsed is None:
        bound = watches.bound_cond(text)
        parsed = bound[0] if bound is not None else None
    if parsed is None or _without_scope(parsed) != _without_scope(saved):
        return None
    scope = parsed.get(FIELD)
    if scope in ('player', 'opponent'):
        return scope

    return None


def _heads(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if value.get('kind') == 'watch' and isinstance(value.get('cond'), dict):
            yield value
        for nested in value.values():
            yield from _heads(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _heads(nested)


def restore(plan: Any, watch: Any) -> dict[str, Any]:
    from app.rules import scripts, triggers

    saved = watch.when['cond']
    if saved.get('event') != 'deal_combat_damage_player':
        return saved
    if saved.get(FIELD) in ('player', 'opponent'):
        return saved
    if (text := watch.when.get('text')) and (scope := _scope_from_text(text, saved)):
        watch.when['cond'] = {**saved, FIELD: scope}
        return watch.when['cond']
    # Do not use the physical card's current incarnation or guess from a name.
    # Stack LKI is the original creating spell at its resolution/departure.
    snap = plan.rules.lki.get(watch.source_object or '')
    if snap is not None and snap.zone == 'stack':
        ch = triggers._lki_characteristics(plan, snap)
        scopes = set()
        for definition in scripts.definitions(ch).values():
            for head in _heads(definition):
                if _without_scope(head['cond']) != _without_scope(saved):
                    continue
                scope = head['cond'].get(FIELD)
                if scope not in ('player', 'opponent') and head.get('text'):
                    scope = _scope_from_text(head['text'], saved)
                if scope in ('player', 'opponent'):
                    scopes.add(scope)
        if len(scopes) == 1:
            watch.when['cond'] = {**saved, FIELD: scopes.pop()}
            return watch.when['cond']
    return saved


def first_result(plan: Any, condition: dict[str, Any], info: dict[str, Any], *,
                 fixed_controller: str | None = None) -> bool | None:
    """Whether this object has an earlier qualifying hit; None is unknown legacy control."""
    from app.rules import history

    batch, oid = int(info.get('batch') or 0), info.get('oid')
    unknown = False
    for fact in history.log_for(plan).facts:
        if fact.kind != 'damage' or fact.object_id != oid or fact.amount <= 0 or not fact.combat \
                or not fact.batch or fact.batch >= batch:
            continue
        if condition.get(FIELD) != 'opponent':
            return False
        historical = fixed_controller if fixed_controller is not None else fact.source_controller \
            if condition.get('subject') == 'self' else None
        if historical is None:
            unknown = True
        elif fact.player != historical:
            return False
    return None if unknown else True


def _first_conditions(condition: dict[str, Any], plan: Any, info: dict[str, Any], *,
                      assume: bool, fixed_controller: str | None = None) -> dict[str, Any]:
    """Substitute only first-time predicates, leaving native subject/qualifier checks intact."""
    if condition.get('event') == 'either':
        return {**condition, 'conds': [_first_conditions(c, plan, info, assume=assume,
                                                       fixed_controller=fixed_controller) for c in condition['conds']]}
    if condition.get('event') != 'deal_combat_damage_player' or not condition.get('first_each_turn'):
        return condition
    result = first_result(plan, condition, info, fixed_controller=fixed_controller)
    if result is None:
        result = assume
    if not result:
        return {'event': 'never', 'subject': 'self'}
    return {k: v for k, v in condition.items() if k != 'first_each_turn'}


def _prune_notices(plan: Any) -> None:
    plan.rules.combat_history_notices = [n for n in plan.rules.combat_history_notices if n.turn == plan.state.turn.number]


def _notice(plan: Any, watcher: Any, oid: str, index: int, name: str) -> None:
    from app.game.rules_state import CombatHistoryNotice

    _prune_notices(plan)
    if not any(n.source_object == oid and n.ability == index and n.controller == watcher.controller
               for n in plan.rules.combat_history_notices):
        plan.rules.combat_history_notices.append(CombatHistoryNotice(source_object=oid, ability=index,
            controller=watcher.controller, turn=plan.state.turn.number, name=name[:500]))


def printed_verdict(plan: Any, condition: dict[str, Any], watcher: Any, fact: Any, *,
                    source_oid: str, index: int, name: str) -> bool:
    from app.rules import triggers

    def has_first(c: dict[str, Any]) -> bool:
        return bool(c.get('first_each_turn') or any(has_first(sub) for sub in c.get('conds', ())))

    if not plan.rules.combat_history_notices and not has_first(condition):
        return triggers._cond_matches(plan, condition, watcher, fact, source_oid=source_oid)
    _prune_notices(plan)
    if any(n.source_object == source_oid and n.ability == index for n in plan.rules.combat_history_notices):
        # Each new controlling player gets their own notice; the old owner's remains.
        if triggers._cond_matches(plan, _first_conditions(condition, plan, fact[4], assume=True), watcher, fact,
                                  source_oid=source_oid):
            _notice(plan, watcher, source_oid, index, name)
        return False
    if fact[0] != 'deal_combat_damage_player':
        return triggers._cond_matches(plan, condition, watcher, fact, source_oid=source_oid)
    lower = triggers._cond_matches(plan, _first_conditions(condition, plan, fact[4], assume=False), watcher, fact,
                                   source_oid=source_oid)
    upper = triggers._cond_matches(plan, _first_conditions(condition, plan, fact[4], assume=True), watcher, fact,
                                   source_oid=source_oid)
    if lower == upper:
        return lower
    _notice(plan, watcher, source_oid, index, name)
    return False


def verdict(plan: Any, watch: Any, watcher: Any, fact: Any, condition: dict[str, Any]) -> bool:
    from app.rules import triggers

    if fact[0] != 'deal_combat_damage_player':
        return triggers._cond_matches(plan, condition, watcher, fact)
    scopes = [condition.get(FIELD)] if condition.get(FIELD) in ('player', 'opponent') else ['player', 'opponent']
    results = {triggers._cond_matches(plan,
        _first_conditions({**condition, FIELD: scope}, plan, fact[4], assume=assume, fixed_controller=watch.controller),
        watcher, fact) for scope in scopes for assume in (False, True)}
    if len(results) == 1:
        return results.pop()
    watch.when['manual_combat_scope'] = True
    watch.when['manual_combat_notice'] = True
    return False  # No fabricated trigger or once-only consumption.


def ask_pending(plan: Any) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if plan.rules.decision is not None:
        return False
    _prune_notices(plan)
    for player in plan.apnap():
        watches = [watch for watch in plan.rules.delayed if watch.controller == player
                   and watch.when.get('manual_combat_notice')]
        notices = [n for n in plan.rules.combat_history_notices if n.controller == player and not n.notified]
        if not watches and not notices:
            continue
        names = ', '.join(dict.fromkeys([*(w.name or 'delayed ability' for w in watches),
                                        *(n.name or 'triggered ability' for n in notices)]))[:100]
        priority = plan.rules.priority
        for watch in watches:
            watch.when['manual_combat_notice'] = False
        for notice in notices:
            notice.notified = True
        decide(plan, player=player, kind='manual_resolution',
               prompt=(f'Older save: {names} lacks its original condition or damage-time controller history. Handle its triggers '
                       'and once-only limit by hand (printed abilities: this turn; delayed watches: remaining duration), then press Done.'),
               options=[DecisionOption(id='done', label='Done')],
               resume={'step': 'combat_scope_legacy_done', 'priority': priority})
        return True
    return False


def legacy_done(plan: Any, decision: Any, chosen: list[str]) -> None:
    old = decision.resume.get('priority')
    plan.rules.priority = old if old in plan.live() else None


RESUME = {'combat_scope_legacy_done': legacy_done}
