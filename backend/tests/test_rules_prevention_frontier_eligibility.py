"""Isolated routing preflight; no production routing or source admission."""
from __future__ import annotations

from app.rules import prevention_frontier_eligibility as entry
from app.rules import replace
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_prevention_frontier_grounding import record, setup


def mark(plan, *, recipient=None, source=None, redirect=False):
    rec = plan.rules.replacements[0]
    rec['op'][entry.MARKER] = True
    if redirect:
        rec['op'] = {'do': 'redirect', 'to': 'pid', 'pid': 'p3', 'limit': 3, 'allocate': True, entry.MARKER: True}
    rec['match'] = {**({'to': {'pids': recipient}} if recipient else {}),
                    **({'source': {'oids': [source]}} if source else {})}
    return rec


def check(plan, events):
    before = plan.state.model_dump_json()
    result = entry.eligible(plan, events, replace.damage_candidates(plan))
    assert plan.state.model_dump_json() == before and plan.rules.decision is None
    return result


def test_no_marker_irrelevant_recipient_and_irrelevant_original_source_leave_native_route(cards):
    plan, _, events = setup(cards)
    assert not check(plan, events)
    rec = mark(plan, recipient=['p3'])
    assert not check(plan, events)
    record(plan, {'do': 'half'}, label='Unrelated native effect')
    assert not check(plan, events)
    rec['match'] = {'source': {'oids': ['other.original.source']}}
    assert not check(plan, events)
    rec['match'] = {'source': {'oids': [events[0]['source_oid']]}}
    assert check(plan, events)


def test_native_redirect_can_enter_marked_recipient_and_cycles_have_no_cap_or_loop(cards):
    plan, _, events = setup(cards)
    mark(plan, recipient=['p3'])
    assert not check(plan, events)
    record(plan, {'do': 'redirect', 'to': 'pid', 'pid': 'p3', 'limit': 1, 'allocate': True}, label='Into the pool')
    record(plan, {'do': 'redirect', 'to': 'pid', 'pid': 'p1', 'limit': 1, 'allocate': True}, label='Back to the original')
    assert check(plan, events)
    plan.rules.replacements[0]['match'] = {'source': {'oids': ['other.source']}}
    assert not check(plan, events)


def test_zero_amount_or_zero_budget_never_routes_unrelated_pool(cards):
    plan, _, events = setup(cards)
    rec = mark(plan)
    assert not check(plan, [{**e, 'amount': 0} for e in events])
    assert not check(plan, [{'amount': 0, 'target': 'no-damage-recipient'}])
    rec['op']['limit'] = 0
    assert not check(plan, events)


def test_unpreventable_prevention_is_irrelevant_but_redirect_remains_applicable(cards):
    plan, _, events = setup(cards)
    mark(plan)
    events = [{**e, 'unpreventable': True} for e in events]
    assert not check(plan, events)
    mark(plan, redirect=True)
    assert check(plan, events)
