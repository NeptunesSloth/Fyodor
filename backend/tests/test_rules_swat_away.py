"""Canonical collateral promotion: owner tuck choices and attacked-player discount."""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.view import decision_view
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_owner_library_choices import answer
from tests.test_rules_owner_library_choices import cards as _cards
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

cards = _cards


def setup(cards):
    return table(cards, ['Swat Away', 'Commandeer'], ['Grizzly Bears', 'Lightning Bolt', 'Sol Ring'])


def test_actual_swat_away_full(cards):
    assert coverage.of_card_data(cards.resolve('Swat Away')).level == 'FULL'


@pytest.mark.parametrize('place', ['top', 'bottom'])
@pytest.mark.parametrize('zone', ['battlefield', 'stack'])
def test_swat_away_owner_selects_top_or_bottom_and_pending_choice_is_private(cards, place, zone):
    s = setup(cards)
    target = put(s, 'Grizzly Bears' if zone == 'battlefield' else 'Lightning Bolt', 'hand' if zone == 'stack' else zone, pid='p2')
    if zone == 'stack':
        wait_priority(s, 'p2')
        mana(s, pid='p2', R=1)
        act(s, 'p2', type='cast_spell', card_id=target.id, targets=['p3'])
        wait_priority(s, 'p1')
    swat = put(s, 'Swat Away', 'hand')
    mana(s, U=2, C=2)
    act(s, 'p1', type='cast_spell', card_id=swat.id, targets=[target.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    for pid in ['p1', 'p3']:
        assert 'options' not in decision_view(s.state, d, pid)
        assert decision_view(s.state, d, pid)['source_id'] is None
    assert {o['id'] for o in decision_view(s.state, d, 'p2')['options']} == {'top', 'bottom'}
    answer(s, 'p2', place)
    assert s.state.zones['p2:library'][0 if place == 'top' else -1] == target.id
    assert s.state.players['p3'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('defender', ['p1', 'p3'])
def test_discount_requires_creature_attacking_caster_not_another_opponent(cards, defender):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    swat = put(s, 'Swat Away', 'hand')
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, (bear, defender), pid='p2')
    wait_priority(s, 'p1')
    mana(s, U=2)
    if defender == 'p3':
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=swat.id, targets=[bear.id])
        mana(s, C=2)
    act(s, 'p1', type='cast_spell', card_id=swat.id, targets=[bear.id])
    answer(s, 'p2', 'bottom')
    assert s.state.zones['p2:library'][-1] == bear.id
    roundtrip(s)


def test_swat_away_cannot_tuck_noncreature_permanent(cards):
    s = setup(cards)
    ring = put(s, 'Sol Ring', 'battlefield', pid='p2')
    swat = put(s, 'Swat Away', 'hand')
    mana(s, U=2, C=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=swat.id, targets=[ring.id])
    assert s.state.cards[swat.id].zone == 'p1:hand'
    roundtrip(s)


def test_swat_away_stolen_spell_is_still_placed_by_its_original_owner(cards):
    from tests.test_rules_narset_rebound import steal_bolt

    s = setup(cards)
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    steal_bolt(s, bolt, player='p1', target='keep')
    swat = put(s, 'Swat Away', 'hand')
    mana(s, U=2, C=2)
    act(s, 'p1', type='cast_spell', card_id=swat.id, targets=[bolt.id])
    answer(s, 'p2', 'top')
    assert s.state.zones['p2:library'][0] == bolt.id
    assert s.state.players['p3'].life == 40
    roundtrip(s)
