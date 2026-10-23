"""First resolved crew/saddle events and crew-cost cardinality use native receipts."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

MIGHTY = ('Whenever this Vehicle becomes crewed for the first time each turn, if it was crewed by exactly two creatures, '
          'it gains "Whenever this creature deals combat damage to a player, draw two cards" until end of turn.')
MINDLINK = ("Whenever this Vehicle becomes crewed for the first time each turn, until end of turn, this Vehicle becomes a copy of "
            "target nonlegendary creature that crewed it this turn, except it's 4/3, it's a Vehicle artifact in addition to its other types, and it has flying.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text not in {MIGHTY, MINDLINK}:
        return None
    text = ability.text.replace(' for the first time each turn', '')
    if ability.text == MIGHTY:
        text = 'Whenever this Vehicle becomes crewed, draw a card.'
    native = scripts.define(replace(ability, text=text), ch)
    if native is None:
        return None
    condition = {**native['cond'], 'first_source80': True, 'first_source_index80': ability.index}
    if ability.text == MIGHTY:
        parsed = scripts.parse_effects('This creature gains "Whenever this creature deals combat damage to a player, draw two cards" until end of turn.')
        if parsed is None:
            return None
        return {**native, 'cond': {**condition, 'crew_exact80': 2}, 'effects': parsed[0]}
    return {**native, 'cond': condition, 'effects': [
        {**effect, 'do': 'mindlink_copy80'} if effect.get('do') == 'become_copy' else effect
        for effect in native['effects']]}


def mindlink_copy(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import copying, effects

    targets = effects._cards(plan, ctx, effect['with'])
    if len(targets) == 1:
        base = copying.characteristics(copying.recipe_of(plan, plan.state.cards[targets[0]]), plan.info)
        # Mindlink's official ruling: an animated noncreature without copiable
        # P/T (unlike a printed Vehicle) cannot receive the 4/3 copy exception.
        # Its existing crew animation then makes the copy a 0/0 creature.
        if not base.is_creature and base.power is None and base.toughness is None:
            effect = {**effect, 'excepts': [{k: v for k, v in ex.items() if k not in {'power', 'toughness'}}
                                           for ex in effect.get('excepts') or []]}
    return copying.become_copy(plan, ctx, effect)


def annotate(plan: Any, facts: list[Any]) -> None:
    turn = plan.state.turn.number
    for kind, _card, _ch, _player, info in facts:
        oid = info.get('oid')
        if kind not in {'crewed', 'saddled'} or not oid:
            continue
        key = 'first80:' + kind + ':' + oid
        info['first_source80'] = False if plan.rules.once_per_turn.get(key) == turn else (
            True if plan.rules.crew_saddle_history_turn80 == turn else None)
        plan.rules.once_per_turn[key] = turn


def matches(plan: Any, condition: dict[str, Any], watcher: Any, fact: Any, source_oid: str | None = None) -> bool:
    from app.game.rules_state import FirstEventHistoryNotice78
    from app.rules import triggers

    native = {k: v for k, v in condition.items() if k not in {'first_source80', 'first_source_index80', 'crew_exact80'}}
    if not triggers._cond_matches(plan, native, watcher, fact, source_oid=source_oid):
        return False
    first = fact[4].get('first_source80')
    if first is False:
        return False
    count = fact[4].get('crew_count80')
    if 'crew_exact80' in condition and count is not None and count != condition['crew_exact80']:
        return False
    if first is True and ('crew_exact80' not in condition or count is not None):
        return True
    # Unknown saved history/payment metadata cannot establish a first qualifying event.
    oid, index, turn = source_oid or plan.oid(watcher), condition['first_source_index80'], plan.state.turn.number
    if not any(n.source_object == oid and n.ability == index and n.controller == watcher.controller and n.turn == turn
               for n in plan.rules.first_event_notices78):
        plan.rules.first_event_notices78.append(FirstEventHistoryNotice78(source_object=oid, ability=index,
            controller=watcher.controller, turn=turn, name=watcher.name[:500]))
    return False
