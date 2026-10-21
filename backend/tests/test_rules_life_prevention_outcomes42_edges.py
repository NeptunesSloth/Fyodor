"""Staged native response, duration, identity and simultaneous combat proofs."""
from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_immortal_coil_outcomes import settle
from tests.test_rules_life_prevention_outcomes42 import cards as cards
from tests.test_rules_life_prevention_outcomes42 import enter_transcendence, game, nemesis_hit
from tests.test_rules_prevention_outcomes import activate, cast, choose
from tests.test_rules_wave30m_durations import to_phase


@pytest.mark.parametrize('angel', [False, True])
def test_transcendence_original_loss_survives_source_departure_without_false_loop(cards, angel):
    s = game(cards)
    if angel:
        put(s, 'Platinum Angel', 'battlefield')
    source = enter_transcendence(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    roundtrip(s)
    settle(s)
    assert ('p1' in s.state.rules.lost) is not angel
    assert s.state.rules.draw_reason is None


def test_transcendence_current_controller_change_breaks_original_blocked_loss_proof(cards):
    s = game(cards)
    put(s, 'Platinum Angel', 'battlefield')
    act(s, 'p2', type='life', player='p2', delta=-30)
    source = enter_transcendence(s)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert not s.state.rules.lost and s.state.rules.draw_reason is None
    assert not s.state.zones.get('stack')


def test_transcendence_actual_ability_removal_breaks_blocked_loop_proof(cards):
    s = game(cards)
    put(s, 'Platinum Angel', 'battlefield')
    put(s, 'Vedalken Orrery', 'battlefield', 'p2')
    source = enter_transcendence(s)
    cast(s, 'Song of the Dryads', [source.id], pid='p2', resolve=False)
    settle(s)
    assert not s.state.rules.lost and s.state.rules.draw_reason is None
    assert not s.state.zones.get('stack')


def test_transcendence_countered_state_trigger_retriggers_before_game_can_progress(cards):
    s = game(cards)
    put(s, 'Platinum Angel', 'battlefield')
    enter_transcendence(s)
    original = s.state.zones['stack'][-1]
    cast(s, 'Stifle', [original], pid='p2', resolve=False)
    for _ in range(12):
        if original not in s.state.zones.get('stack', []):
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert original not in s.state.zones.get('stack', [])
    new = s.state.rules.stack[s.state.zones['stack'][-1]]
    assert new.effects[0]['do'] == 'state_trigger'
    assert new.effects[1]['do'] == 'transcendence_state_loss'
    assert not s.state.rules.lost and s.state.rules.draw_reason is None
    roundtrip(s)


@pytest.mark.parametrize('permanent', [False, True])
def test_life_lock_duration_follows_native_turn_progression(cards, permanent):
    s = game(cards)
    if permanent:
        nemesis_hit(s)
        choose(s, ['p2'])
    else:
        cast(s, 'Flames of the Blood Hand', ['p2'])
    turn = s.state.turn.number
    to_phase(s, 'main1', turn=turn + 1)
    roundtrip(s)
    cast(s, 'Revitalize', pid='p2')
    assert s.state.players['p2'].life == (37 if permanent else 39)


def test_flames_all_illegal_target_creates_no_life_replacement(cards):
    s = game(cards)
    walker = put(s, 'Narset, Parter of Veils', 'battlefield', 'p2')
    act(s, 'p2', type='counter', card_ids=[walker.id], kind='loyalty', delta=3)
    cast(s, 'Flames of the Blood Hand', [walker.id], resolve=False)
    act(s, 'p2', type='move', card_ids=[walker.id], to={'player': 'p2', 'zone': 'hand'})
    settle(s)
    assert not any(r.get('event') == 'life' for r in s.state.rules.replacements)
    cast(s, 'Revitalize', pid='p2')
    assert s.state.players['p2'].life == 43


def test_flames_planeswalker_controller_is_read_at_resolution_before_damage(cards):
    s = game(cards)
    walker = put(s, 'Narset, Parter of Veils', 'battlefield', 'p2')
    act(s, 'p2', type='counter', card_ids=[walker.id], kind='loyalty', delta=3)
    cast(s, 'Flames of the Blood Hand', [walker.id], resolve=False)
    act(s, 'p2', type='set_controller', card_ids=[walker.id], player='p3')
    settle(s)
    cast(s, 'Revitalize', pid='p2')
    cast(s, 'Revitalize', pid='p3')
    assert s.state.players['p2'].life == 43 and s.state.players['p3'].life == 40


def test_nemesis_exact_original_self_is_excluded_while_nonlethal_source_remains(cards):
    s = game(cards)
    source = put(s, 'Screaming Nemesis', 'battlefield')
    pestilence = put(s, 'Pestilence', 'battlefield', 'p2')
    activate(s, pestilence, 'each creature', pid='p2')
    assert source.id not in {o.id for o in s.state.rules.decision.options}
    choose(s, ['p2'])
    assert s.state.players['p2'].life == 38
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert [r['player'] for r in s.state.rules.cant_gain] == ['p2']


def test_nemesis_native_haste_attack_and_two_blocker_damage_trigger_once_for_total(cards):
    from tests.test_rules_banding import block, damage_choice, divide, until_block

    s = game(cards)
    source = put(s, 'Screaming Nemesis', 'battlefield')
    first = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    second = put(s, 'Centaur Courser', 'battlefield', 'p2')
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    until_block(s)
    block(s, [(first, source), (second, source)])
    damage_choice(s)
    divide(s, {first.id: 2, second.id: 1})
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    choose(s, ['p3'])
    assert s.state.players['p3'].life == 35
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    assert len(s.state.rules.cant_gain) == 1
    roundtrip(s)


def test_countered_nemesis_trigger_creates_no_life_lock(cards):
    s = game(cards)
    nemesis_hit(s)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    original = s.state.zones['stack'][-1]
    cast(s, 'Stifle', [original], pid='p2')
    assert not s.state.rules.cant_gain and s.state.players['p2'].life == 40


def test_nemesis_lifelink_gain_finishes_before_new_prohibition_is_installed(cards):
    s = game(cards)
    source = put(s, 'Screaming Nemesis', 'battlefield')
    collar = put(s, 'Basilisk Collar', 'battlefield')
    activate(s, collar, 'Equip {2}', [source.id])
    pestilence = put(s, 'Pestilence', 'battlefield', 'p2')
    activate(s, pestilence, 'each creature', pid='p2')
    choose(s, ['p1'])
    # Pestilence loses1; Nemesis loses1 and gains1 via lifelink before the lock.
    assert s.state.players['p1'].life == 39
    assert [r['player'] for r in s.state.rules.cant_gain] == ['p1']
    cast(s, 'Revitalize')
    assert s.state.players['p1'].life == 39
    roundtrip(s)


def test_nemesis_positive_damage_without_life_loss_still_creates_lasting_lock(cards):
    s = game(cards)
    emperor = put(s, 'Platinum Emperion', 'battlefield', 'p2')
    nemesis_hit(s)
    choose(s, ['p2'])
    assert s.state.players['p2'].life == 40  # Actual damage was dealt despite no life loss.
    assert [r['player'] for r in s.state.rules.cant_gain] == ['p2']
    act(s, 'p2', type='move', card_ids=[emperor.id], to={'player': 'p2', 'zone': 'hand'})
    cast(s, 'Revitalize', pid='p2')
    assert s.state.players['p2'].life == 40
    roundtrip(s)
