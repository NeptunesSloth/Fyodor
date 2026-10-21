"""Isolated exact static source-batch candidate/kernel; no production card/bridge hooks."""
from __future__ import annotations

from dataclasses import replace as changed

import pytest

from app.rules import prevention_frontier_constraints as affine
from app.rules import prevention_frontier_grounding as native
from app.rules import prevention_frontier_prototype as model
from app.rules import replace
from app.rules import source_batch_prevention as scoped
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_designations import put
from tests.test_rules_prevention_outcomes import game

TEXT = 'If a creature would deal combat damage to you and/or one or more creatures you control, prevent X of that damage, where X is the number of age counters on this enchantment.'


def setup(cards, age=2):
    s = game(cards)
    cover = put(s, 'Cover of Winter', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[cover.id], kind='age', delta=age)
    first = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    second = put(s, 'Centaur Courser', 'battlefield', 'p2')
    blocker = put(s, 'White Knight', 'battlefield')
    plan = Plan(s.state, 'p1', cards, None)
    candidate = next(c for c in replace.damage_candidates(plan) if c.source_card == cover.id and c.op.get('budget_scope'))
    operation = model.Operation(candidate.id, 'pool', pool=candidate.id)
    rows = [('one-blocker', first.id, blocker.id, 2), ('one-player', first.id, 'p1', 3), ('two-player', second.id, 'p1', 3)]
    packets = tuple(model.Packet(row, plan.oid(source), target, plan.oid(target) if target in plan.state.cards else '',
                                 'p1', amount, (operation,)) for row, source, target, amount in rows)
    frame = model.Frontier('first-strike-occurrence', packets, (model.Pool(candidate.id, 'p1', age, scope='source_batch'),))
    events = [{'kind': 'damage', 'amount': amount, 'source_card': source, 'source_oid': plan.oid(source), 'target': target,
               'target_oid': plan.oid(target) if target in plan.state.cards else None, 'combat': True, '_damage_lineage': row,
               'src': replace.source_info(plan, source, plan.oid(source), plan.ch(plan.state.cards[source]), 'p2')}
              for row, source, target, amount in rows]
    return plan, frame, events, candidate


def selected(frame):
    return next(s for s in model.solutions(frame)
                if {row: n for selection in s.allocations for row, n in selection.vector}
                == {'one-blocker': 1, 'one-player': 1, 'two-player': 2})


def test_original_creature_source_shares_one_budget_across_blocker_and_player_but_other_source_independent(cards):
    plan, frame, events, candidate = setup(cards)
    solved = selected(frame)
    prefix = tuple((sel.pool_group, row, n) for sel in solved.allocations for row, n in sel.vector)
    assert affine.witness(frame, prefix) == solved
    result = native.ground(plan, native.capture(plan, frame, events), solved)
    assert [e['amount'] for e in result.events] == [1, 2, 1]
    assert sum(r['amount'] for r in result.receipts) == 4
    assert len(result.shields) == 2 and all(k.startswith('source_limited:') and n == 0 for k, n in result.shields.items())
    assert all(e['applied'] == [candidate.id] for e in result.events)
    assert native.ground(plan, native.capture(plan, frame, events), solved, reverse=True) == result


def test_source_batch_keys_do_not_commit_or_persist_between_damage_occurrences(cards):
    plan, frame, events, candidate = setup(cards)
    result = native.ground(plan, native.capture(plan, frame, events), selected(frame))
    before = plan.state.model_dump_json()
    replace.commit_shields(plan, result.shields)
    assert plan.state.model_dump_json() == before
    assert plan.state.cards[candidate.source_card].counters['age'] == 2
    regular = changed(frame, batch='regular-damage-occurrence')
    again = native.ground(plan, native.capture(plan, regular, events), selected(regular))
    assert again == result  # Fresh native simulation replenishes every source's full static budget.


def test_current_age_counter_change_invalidates_the_native_static_snapshot(cards):
    plan, frame, events, candidate = setup(cards)
    saved = native.capture(plan, frame, events)
    plan.state.cards[candidate.source_card].counters['age'] = 3
    with pytest.raises(ValueError, match='changed'):
        native.ground(plan, saved, selected(frame))


@pytest.mark.parametrize('combat', [False, True])
def test_noncombat_or_noncreature_source_does_not_apply_static_combat_pool(cards, combat):
    plan, frame, events, _ = setup(cards)
    for event in events:
        event['combat'] = combat
        if combat:
            event['src']['types'] = ['Artifact']
    frame = changed(frame, packets=tuple(changed(p, operations=()) for p in frame.packets))
    solved, = model.solutions(frame)
    result = native.ground(plan, native.capture(plan, frame, events), solved)
    assert sum(e['amount'] for e in result.events) == 8
    assert not result.receipts and not result.shields


def test_zero_age_budget_prevents_nothing_without_applying_phantom_candidate(cards):
    plan, frame, events, _ = setup(cards, age=0)
    solved, = model.solutions(frame)
    result = native.ground(plan, native.capture(plan, frame, events), solved)
    assert sum(e['amount'] for e in result.events) == 8
    assert not result.receipts and not result.shields
    assert all(not e.get('applied') for e in result.events)


def test_scoped_key_requires_static_candidate_and_original_source_oid(cards):
    _, _, events, candidate = setup(cards)
    assert scoped.budget_key(candidate, events[0]) == scoped.budget_key(candidate, events[1])
    assert scoped.budget_key(candidate, events[0]) != scoped.budget_key(candidate, events[2])
    with pytest.raises(ValueError, match='static'):
        scoped.budget_key(changed(candidate, id='r:unsupported-turn-record'), events[0])
    with pytest.raises(ValueError, match='original'):
        scoped.budget_key(candidate, {**events[0], 'source_oid': None})
