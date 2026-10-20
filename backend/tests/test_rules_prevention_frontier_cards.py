"""Exact full B recipes through production source and joint bridge hooks."""
from __future__ import annotations

import pytest

from app.rules import alt_costs, replace
from app.rules import prevention_frontier_cards as leaf
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_prevention_outcomes import cast, game, source_choice
from tests.test_rules_shoal_nonmana_x import cards as cards


@pytest.mark.parametrize(('name', 'limit', 'redirect', 'source'), [
    ("Harm's Way", 2, True, True), ('Shining Shoal', 4, True, True),
    ('Divine Deflection', 4, False, False), ('Refraction Trap', 3, False, True)])
def test_actual_spell_creates_exact_finite_source_recipient_and_target_records(cards, name, limit, redirect, source):
    s = game(cards)
    chosen = put(s, 'Pestilence', 'battlefield', 'p2')
    spell = cast(s, name, ['p3'], **({'x_value': 4} if name in ('Shining Shoal', 'Divine Deflection') else {}))
    if source:
        assert s.state.rules.decision.resume['step'] == leaf.SOURCE
        roundtrip(s)
        source_choice(s, chosen)
    records = [r for r in s.state.rules.replacements if r.get('source_card') == spell.id]
    assert len(records) == 1
    record = records[0]
    assert record['controller'] == 'p1' and record['source'] != s.state.rules.object_id(spell.id)
    assert record['op']['limit'] == limit and record['op']['allocate'] and not record['op'].get('once')
    assert record['op']['do'] == ('redirect' if redirect else 'finite_prevention')
    assert record['match']['to']['players'] == 'you' and record['match']['to']['objects']
    if source:
        assert record['match']['source']['oids'] == [s.state.rules.object_id(chosen.id)]
    else:
        assert 'source' not in record['match']
    if redirect:
        assert record['op']['to'] == 'pid' and record['op']['pid'] == 'p3'
    else:
        assert record['op']['prevention'] and record['op']['rider']['if']
        assert record['op']['rider']['context']['targets'][0]['id'] == 'p3'
    assert s.state.rules.decision is None and s.state.cards[spell.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_exact_cover_static_reads_current_age_with_original_native_candidate_identity(cards):
    s = game(cards)
    cover = put(s, 'Cover of Winter', 'battlefield')
    for age in (0, 1, 3):
        act(s, 'p1', type='counter', card_ids=[cover.id], kind='age', delta=age - s.state.cards[cover.id].counters.get('age', 0))
        plan = Plan(s.state, 'p1', cards, None)
        candidate = next(c for c in replace.damage_candidates(plan) if c.source_card == cover.id)
        assert candidate.id.startswith('s:' + plan.oid(cover))
        assert candidate.op['limit'] == age and candidate.op['budget_scope'] == 'source_batch'
        assert 'frontier_age' not in candidate.op and candidate.match['combat'] is True


def test_refraction_printed_red_instant_condition_native_alternate_cost(cards):
    s = game(cards)
    trap = put(s, 'Refraction Trap', 'hand')
    plan = Plan(s.state, 'p1', cards, None)
    assert alt_costs.offers(plan.state, 'p1', plan.state.cards[trap.id], plan.ch(plan.state.cards[trap.id]), plan.info) == []
    cast(s, 'Lightning Bolt', ['p3'], pid='p2')
    wait_priority(s, 'p1')
    plan = Plan(s.state, 'p1', cards, None)
    offer, = alt_costs.offers(plan.state, 'p1', plan.state.cards[trap.id], plan.ch(plan.state.cards[trap.id]), plan.info)
    assert offer.alt.mana == '{W}'
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
    act(s, 'p1', type='cast_spell', card_id=trap.id, targets=['p2'], alt_cost=offer.key, sources=[])
    receipt = s.state.rules.payments[s.state.rules.object_id(trap.id)]
    assert receipt.mana_spent == {'W': 1}
    settle(s)
    if s.state.rules.decision:
        assert s.state.rules.decision.resume['step'] == leaf.SOURCE


@pytest.mark.parametrize('name', ['Cover of Winter', "Harm's Way", 'Shining Shoal', 'Divine Deflection', 'Refraction Trap'])
def test_production_whole_card_coverage_requires_all_printed_lines(cards, name):
    from app.rules import coverage
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_finite_static_coverage_does_not_admit_unmarked_or_changed_scope_definitions(cards):
    import copy

    from app.rules import coverage
    s = game(cards)
    holder = put(s, 'Cover of Winter', 'battlefield')
    p = Plan(s.state, 'p1', cards, None)
    ab = next(a for a in p.ch(p.state.cards[holder.id]).abilities if a.kind == 'static')
    exact = leaf.definition(ab, p.ch(p.state.cards[holder.id]))
    for field in ('joint_prevention', 'frontier_age', 'budget_scope'):
        other = copy.deepcopy(exact)
        other['op'].pop(field)
        assert coverage.stage2_supported(other) is False
    other = copy.deepcopy(exact)
    other['match']['combat'] = False
    assert coverage.stage2_supported(other) is False
