"""Narset grants rebound to the next matching hand-cast spell through a real delayed trigger."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Narset Transcendent'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/narset_rebound_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




def setup(cards, *, source_leaves=False, activate=True):
    s = table(cards, [NAME, 'Lightning Bolt', 'Deep Analysis', 'One with the Multiverse', 'Omniscience', 'Grizzly Bears', 'Light Up the Stage', 'Commandeer', 'Mindleech Mass'], ['Counterspell', 'Stifle', 'Commandeer', 'Staggershock'])
    source = put(s, NAME, 'hand')
    mana(s, W=1, U=1, C=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[])
    settle(s)
    if activate:
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
        settle(s)
    if source_leaves:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    roundtrip(s)
    return s, source


def bolt_cast(s, *, free=False):
    bolt = put(s, 'Lightning Bolt', 'hand')
    if not free:
        mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'], free=free)
    return bolt


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('source_leaves', [False, True])
def test_rebound_exiles_successful_spell_and_next_upkeep_can_cast_once(cards, source_leaves):
    s, _ = setup(cards, source_leaves=source_leaves)
    bolt = bolt_cast(s)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    assert s.state.players['p2'].life == 37
    roundtrip(s)
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'choose_one' and 'Rebound' in d.prompt
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
    d = s.state.rules.decision
    if d:
        assert any(o.id == 'p2' for o in d.options)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    assert s.state.players['p2'].life == 34
    assert not s.state.rules.rebounding
    roundtrip(s)


@pytest.mark.parametrize('after_grant', [False, True])
def test_counter_original_before_or_after_grant_never_rebounds(cards, after_grant):
    s, _ = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    bolt = bolt_cast(s)
    if after_grant:
        for _ in range(30):
            if len(s.state.zones.get('stack', [])) == 1:
                break
            act(s, s.state.rules.priority, type='pass_priority')
        from app.rules.plan import Plan
        assert 'rebound' in Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[bolt.id]).keywords
        roundtrip(s)
    counter = put(s, 'Counterspell', 'hand', pid='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[bolt.id])
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    assert not s.state.rules.rebounding and not s.state.rules.rebound_cast
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_free_hand_cast_still_rebounds(cards):
    s, _ = setup(cards)
    put(s, 'Omniscience', 'battlefield')
    bolt = bolt_cast(s, free=True)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    roundtrip(s)


def test_countering_delayed_grant_uses_up_watch_without_granting(cards):
    s, _ = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    bolt = bolt_cast(s)
    grant = next(cid for cid in s.state.zones['stack'] if cid != bolt.id)
    stifle = put(s, 'Stifle', 'hand', pid='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', U=1)
    act(s, 'p2', type='cast_spell', card_id=stifle.id, targets=[grant])
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    assert not s.state.rules.rebounding
    # Reusing the same physical card produces a new spell, without another watch.
    bolt_cast(s)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_graveyard_flashback_does_not_consume_hand_only_watch(cards):
    s, _ = setup(cards)
    analysis = put(s, 'Deep Analysis', 'graveyard')
    mana(s, U=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=analysis.id, targets=['p1'])
    settle(s)
    assert s.state.cards[analysis.id].zone == 'p1:exile'
    assert any(t.when.get('kind') == 'watch' for t in s.state.rules.delayed)
    bolt = bolt_cast(s)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    roundtrip(s)


def test_library_cast_does_not_consume_hand_only_watch(cards):
    s, _ = setup(cards)
    put(s, 'One with the Multiverse', 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'library')
    act(s, 'p1', type='move', card_ids=[bolt.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'], free=True)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    assert any(t.when.get('kind') == 'watch' for t in s.state.rules.delayed)
    bolt_cast(s)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    roundtrip(s)


def test_unused_watch_expires_at_end_of_turn(cards):
    s, _ = setup(cards)
    to_phase(s, 'main1', turn=4)
    bolt = bolt_cast(s)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    assert not s.state.rules.rebounding
    roundtrip(s)


def test_declining_upkeep_cast_leaves_card_exiled_without_later_offer(cards):
    s, _ = setup(cards)
    bolt = bolt_cast(s)
    settle(s)
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and 'Rebound' in d.prompt
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['no'])
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    assert not s.state.rules.rebounding and bolt.id not in s.state.rules.free_casts
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('stage', ['before_upkeep', 'upkeep_trigger', 'offered'])
def test_rebound_never_follows_a_new_object_returning_to_exile(cards, stage):
    s, _ = setup(cards)
    bolt = bolt_cast(s)
    settle(s)
    original = s.state.rules.object_id(bolt.id)
    assert s.state.rules.rebound_objects[bolt.id] == original
    if stage != 'before_upkeep':
        to_phase(s, 'upkeep', turn=4)
        assert s.state.zones['stack']
        if stage == 'offered':
            settle(s)
            assert s.state.rules.decision is not None
    decision = s.state.rules.decision
    roundtrip(s)
    act(s, 'p1', type='move', card_ids=[bolt.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[bolt.id], to={'player': 'p1', 'zone': 'exile'})
    assert s.state.rules.object_id(bolt.id) != original
    if stage == 'before_upkeep':
        to_phase(s, 'upkeep', turn=4)
    elif stage == 'offered':
        act(s, 'p1', type='choose', decision_id=decision.id, option_ids=['yes'])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    assert s.state.players['p2'].life == 37
    assert not s.state.rules.rebounding and not s.state.rules.rebound_objects
    assert bolt.id not in s.state.rules.free_casts
    roundtrip(s)


def test_exile_cast_does_not_consume_hand_only_watch(cards):
    s, source = setup(cards, activate=False)
    bolt = put(s, 'Lightning Bolt', 'library')
    act(s, 'p1', type='move', card_ids=[bolt.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    light = put(s, 'Light Up the Stage', 'hand')
    mana(s, R=1, C=2)
    act(s, 'p1', type='cast_spell', card_id=light.id, targets=[])
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    assert any(t.when.get('kind') == 'watch' for t in s.state.rules.delayed)
    bolt_cast(s)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    roundtrip(s)


def steal_bolt(s, spell, *, player='p2', target='p3'):
    steal = put(s, 'Commandeer', 'hand', pid=player)
    wait_priority(s, player)
    mana(s, pid=player, C=5, U=2)
    act(s, player, type='cast_spell', card_id=steal.id, targets=[spell.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == player and s.state.cards[spell.id].controller == player
    act(s, player, type='choose', decision_id=d.id, option_ids=[target])


@pytest.mark.parametrize('after_grant', [False, True])
def test_actual_commandeer_disables_rebound_when_new_controller_did_not_cast_from_own_hand(cards, after_grant):
    s, _ = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    bolt = bolt_cast(s)
    if after_grant:
        for _ in range(30):
            if len(s.state.zones.get('stack', [])) == 1:
                break
            act(s, s.state.rules.priority, type='pass_priority')
    steal_bolt(s, bolt)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    assert s.state.players['p3'].life == 37
    assert not s.state.rules.rebounding and not s.state.rules.rebound_cast
    roundtrip(s)


def test_actual_commandeer_returning_control_before_resolution_restores_rebound(cards):
    s, _ = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    bolt = bolt_cast(s)
    steal_bolt(s, bolt)
    steal_bolt(s, bolt, player='p1', target='p2')
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    assert s.state.rules.rebound_controllers[bolt.id] == 'p1'
    roundtrip(s)


@pytest.mark.parametrize('hand_owner_takes_control', [False, True])
def test_actual_mindleech_opponent_hand_cast_rebound_uses_current_spell_controller(cards, hand_owner_takes_control):
    from tests.test_rules_conditionals import until_asked
    from tests.test_rules_wave33a_turn_triggers import attack
    from tests.test_rules_wave53a_events import mass_prompt

    s, source = setup(cards, activate=False)
    mass = put(s, 'Mindleech Mass', 'battlefield')
    stag = put(s, 'Staggershock', 'hand', pid='p2')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    attack(s, mass)
    d = mass_prompt(s)
    while d.kind == 'confirm' and 'look at the hand' not in d.prompt:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
        d = mass_prompt(s)
    assert 'look at the hand' in d.prompt
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['ok'])
    d = until_asked(s)
    assert stag.id in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[stag.id])
    d = s.state.rules.decision
    assert d and 'p3' in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    record = s.state.rules.payments[s.state.rules.object_id(stag.id)]
    assert record.cast_from == 'hand' and record.cast_from_player == 'p2' and record.controller == 'p1'
    assert any(t.when.get('kind') == 'watch' for t in s.state.rules.delayed)  # Not from Narset controller's hand.
    roundtrip(s)
    if hand_owner_takes_control:
        steal_bolt(s, stag, player='p2', target='p1')
    settle(s)
    assert s.state.cards[stag.id].zone == ('p2:exile' if hand_owner_takes_control else 'p2:graveyard')
    if hand_owner_takes_control:
        assert s.state.rules.rebound_controllers[stag.id] == 'p2'
        to_phase(s, 'upkeep', turn=5)
        settle(s)
        d = s.state.rules.decision
        assert d and d.player == 'p2' and 'Rebound' in d.prompt
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=['no'])
        settle(s)
    # A qualifying hand cast later still consumes Narset's original watcher.
    if s.state.turn.active_player == 'p1':
        bolt = bolt_cast(s)
        settle(s)
        assert s.state.cards[bolt.id].zone == 'p1:exile'
    roundtrip(s)


def test_changing_narset_controller_does_not_change_existing_watch_controller(cards):
    s, source = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    bolt = bolt_cast(s)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    assert s.state.rules.rebound_controllers[bolt.id] == 'p1'
    roundtrip(s)


def test_older_saved_cast_and_pending_rebound_use_compatible_owner_fallback(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s, _ = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    bolt = bolt_cast(s)
    old = s.state.model_dump(mode='json')
    for record in old['rules']['payments'].values():
        record.pop('cast_from_player', None)
    s = GameSession(GameState.model_validate(old), cards=cards)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    old = s.state.model_dump(mode='json')
    old['rules'].pop('rebound_controllers', None)
    old['rules'].pop('rebound_objects', None)
    s = GameSession(GameState.model_validate(old), cards=cards)
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1' and 'Rebound' in d.prompt
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['no'])
    settle(s)
    roundtrip(s)
