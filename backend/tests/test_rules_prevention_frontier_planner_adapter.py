"""Opt-in native DamageOutcome/commit proof; production routing remains absent."""
from __future__ import annotations

from dataclasses import replace as changed

import pytest

from app.rules import effects, replace
from app.rules import prevention_frontier_joint_draft as joint
from app.rules import prevention_frontier_journal as journal
from app.rules import prevention_frontier_planner_adapter as adapter
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_prevention_frontier_grounding import setup
from tests.test_rules_prevention_frontier_journal import finish


def completed(plan, events):
    saved = journal.start(plan, events, batch='native-adapter')
    if all(event['amount'] == 4 for event in events) and all(rec['op']['do'] == 'finite_prevention' for rec in plan.rules.replacements):
        ids = ['r:' + rec['id'] for rec in plan.rules.replacements]
        wanted = {(ids[0], 'left'): 1, (ids[0], 'right'): 2, (ids[1], 'left'): 2, (ids[1], 'right'): 1}
        for _ in range(12):
            q = journal.question(plan, saved)
            if isinstance(q, joint.Completed):
                return q
            if q.kind == 'order':
                selected = ids[0] if q.leaf == 'left' else ids[1]
                saved = journal.choose_order(plan, saved, selected, q.actor)
            else:
                saved = journal.choose_amount(plan, saved, wanted[q.candidate, q.leaf], q.actor)
        raise AssertionError('Small native interior split did not finish')
    _, result = finish(plan, saved)
    return result


def native_outcome(plan, events, result, monkeypatch):
    def staged(p, incoming, **kwargs):
        return adapter.damage_plan(p, result, incoming)
    monkeypatch.setattr(replace, 'plan_damage', staged)
    out = replace.damage_outcome(plan, events, answers={}, order=None, ask=True)
    assert isinstance(out, replace.DamageOutcome)
    return out


def test_proved_native_plan_conversion_preserves_results_receipts_riders_and_commit_once(cards, monkeypatch):
    plan, frame, events = setup(cards)
    result = completed(plan, events)
    untouched = plan.state.model_dump_json()
    out = native_outcome(plan, events, result, monkeypatch)
    assert plan.state.model_dump_json() == untouched
    assert out.players == {'p1': 1} and out.creatures == {events[1]['target']: 1}
    assert sum(r['amount'] for r in out.preventions) == 6 and sum(r['n'] for r in out.riders) == 6
    assert replace.do_damage(plan, out, actor='p1', combat=False)
    assert plan.state.players['p1'].life == 39
    assert plan.state.players['p2'].life == 43 and plan.state.players['p3'].life == 43
    assert plan.state.cards[events[1]['target']].damage == 1
    assert not plan.rules.replacements and not plan.rules.prevention
    assert plan.rules.decision is None


def test_positive_damage_lifelink_is_native_after_shared_prevention(cards, monkeypatch):
    plan, frame, events = setup(cards, source_name="Healer's Hawk")
    source = plan.state.cards[events[0]['source_card']]
    ch = plan.ch(source)
    for event in events:
        event['kw'] = sorted(ch.keywords & effects._DAMAGE_KEYWORDS)
        event['lkey'] = source.id
    result = completed(plan, events)
    out = native_outcome(plan, events, result, monkeypatch)
    assert out.lifelink == {source.id: 2}
    assert replace.do_damage(plan, out, actor='p1', combat=False)
    assert plan.state.players['p2'].life == 45 and plan.state.players['p3'].life == 43
    assert plan.state.players['p1'].life == 39


def test_fully_prevented_zero_still_commits_native_receipts_and_immediate_riders(cards, monkeypatch):
    plan, frame, events = setup(cards)
    for event in events:
        event['amount'] = 2
    result = completed(plan, events)
    out = native_outcome(plan, events, result, monkeypatch)
    assert not out.events and sum(r['amount'] for r in out.preventions) == 4
    assert replace.do_damage(plan, out, actor='p1', combat=False)
    assert plan.state.players['p1'].life == 40
    assert plan.state.players['p2'].life + plan.state.players['p3'].life == 84
    assert not plan.state.cards[events[1]['target']].damage


def test_native_redirect_terminal_order_and_original_source_are_preserved(cards):
    plan, frame, events = setup(cards, redirects=True)
    result = completed(plan, events)
    converted = adapter.damage_plan(plan, result, events)
    assert sum(e['amount'] for e in converted.events) == 8
    positions = [events.index(next(original for original in events if original['_damage_lineage'] == e['_damage_lineage']))
                 for e in converted.events]
    assert positions == sorted(positions)
    assert all(e['source_oid'] == events[0]['source_oid'] and e['src'] == events[0]['src'] for e in converted.events)
    assert converted.notes and not converted.planner.left


def test_wrong_batch_or_forged_solution_is_rejected_before_any_commit(cards):
    plan, frame, events = setup(cards)
    result = completed(plan, events)
    before = plan.state.model_dump_json()
    changed_events = [{**events[0], 'amount': 5}, events[1]]
    with pytest.raises(ValueError, match='caller differs'):
        adapter.damage_plan(plan, result, changed_events)
    forged = changed(result, grounded=changed(result.grounded, receipts=()))
    with pytest.raises(ValueError, match='solution changed'):
        adapter.damage_plan(plan, forged, events)
    assert plan.state.model_dump_json() == before
