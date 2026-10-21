"""Wandering Archaic and APNAP private library choices."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/wandering_archaic_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Wandering Archaic // Explore the Vastlands'


def test_both_faces_are_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def explore(cards):
    s = table(cards, [NAME, 'Lightning Bolt', 'Counterspell', 'Perilous Myr'], ['Lightning Bolt', 'Counterspell', 'Perilous Myr'])
    source = put(s, NAME, 'hand')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
    d = until_asked(s)
    return s, d


def test_explore_private_apnap_zero_reveals_still_gain_life(cards):
    s, d = explore(cards)
    for player in ['p1', 'p2', 'p3']:
        assert d.kind == 'choose_cards' and d.player == player
        assert s.view('p2' if player != 'p2' else 'p1')['rules']['decision']['kind'] == 'waiting'
        roundtrip(s)
        act(s, player, type='choose', decision_id=d.id, option_ids=[])
        d = s.state.rules.decision
    settle(s)
    assert all(p.life == 43 for p in s.state.players.values())
    roundtrip(s)


def test_explore_reveals_now_but_defers_hand_moves_and_rejects_same_category(cards):
    s, d = explore(cards)
    # Default p1 library contains lands as well as the spell and creature fixtures.
    lands = [o.id for o in d.options if 'Land' in cards.resolve(s.state.cards[o.id].name)['type_line']]
    assert len(lands) >= 2
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=lands[:2])
    chosen = lands[0]
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[chosen])
    assert s.state.cards[chosen].zone == 'p1:library'
    assert s.state.rules.decision.player == 'p2'
    roundtrip(s)
    for p in ['p2', 'p3']:
        d = s.state.rules.decision
        act(s, p, type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.cards[chosen].zone == 'p1:hand'
    assert all(p.life == 43 for p in s.state.players.values())
    roundtrip(s)


@pytest.mark.parametrize('pay,copy', [(True, False), (False, False), (False, True)])
def test_front_opponent_pays_before_controller_optional_copy(cards, pay, copy):
    s = table(cards, [NAME], ['Lightning Bolt'])
    source = put(s, NAME, 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1, C=2)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    d = until_asked(s)
    assert d.player == 'p2' and d.resume['step'] == 'pay_or_sacrifice'
    roundtrip(s)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay' if pay else 'decline'])
    if not pay:
        d = s.state.rules.decision
        assert d.player == 'p1' and d.resume['step'] == 'pay_or_sacrifice'
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay' if copy else 'decline'])
        if copy:
            d = s.state.rules.decision
            assert d.player == 'p1'
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    settle(s)
    assert s.state.players['p3'].life == 37
    assert s.state.players['p2'].life == (37 if copy else 40)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('selected_names', [[], ['Forest'], ['Lightning Bolt'], ['Counterspell'], ['Forest', 'Lightning Bolt']])
def test_explore_per_player_categories_and_unrevealed_remainder_privacy(cards, selected_names):
    s = table(cards, [NAME, 'Lightning Bolt', 'Counterspell', 'Perilous Myr', 'Island'], ['Lightning Bolt'])
    source = put(s, NAME, 'hand')
    looked = [put(s, n, 'hand') for n in ['Forest', 'Lightning Bolt', 'Counterspell', 'Perilous Myr', 'Island']]
    act(s, 'p1', type='move', card_ids=[c.id for c in looked], to={'player': 'p1', 'zone': 'library'}, position='top')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
    d = until_asked(s)
    assert all(s.view('p1')['cards'].get(c.id, {}).get('name') for c in looked)
    assert all(not s.view('p2')['cards'].get(c.id, {}).get('name') for c in looked)
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[looked[1].id, looked[2].id])
    chosen = []
    for name in selected_names:
        chosen.append(next(c.id for c in looked if c.name == name and c.id not in chosen))
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=chosen)
    assert all(s.view('p2')['cards'].get(cid, {}).get('name') for cid in chosen)
    assert all(s.state.cards[c.id].zone == 'p1:library' for c in looked)
    for p in ['p2', 'p3']:
        d = s.state.rules.decision
        act(s, p, type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert {c.id for c in looked if s.state.cards[c.id].zone == 'p1:hand'} == set(chosen)
    remaining = set(c.id for c in looked) - set(chosen)
    assert set(s.state.zones['p1:library'][-len(remaining):]) == remaining
    assert all(not s.view('p2')['cards'].get(cid, {}).get('name') for cid in remaining)
    roundtrip(s)


def test_explore_empty_libraries_still_all_gain_three(cards):
    s = table(cards, [NAME])
    source = put(s, NAME, 'hand')
    for p in ['p1', 'p2', 'p3']:
        act(s, 'p1', type='move', card_ids=list(s.state.zones[f'{p}:library']), to={'player': p, 'zone': 'hand'})
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
    d = until_asked(s)
    for p in ['p1', 'p2', 'p3']:
        assert d.player == p and not d.options and d.max_choices == 0
        roundtrip(s)
        act(s, p, type='choose', decision_id=d.id, option_ids=[])
        d = s.state.rules.decision
    settle(s)
    assert all(p.life == 43 for p in s.state.players.values())
    roundtrip(s)


def test_explore_apnap_follows_the_active_turn_order(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [], [NAME])
    to_phase(s, 'main1', turn=2)
    source = put(s, NAME, 'hand', 'p2')
    mana(s, 'p2', C=3)
    act(s, 'p2', type='cast_spell', card_id=source.id, face=1)
    d = until_asked(s)
    for p in ['p2', 'p3', 'p1']:
        assert d.player == p
        act(s, p, type='choose', decision_id=d.id, option_ids=[])
        d = s.state.rules.decision
    settle(s)
    assert all(p.life == 43 for p in s.state.players.values())
    roundtrip(s)


@pytest.mark.parametrize('remove_original', [False, True])
def test_front_source_can_leave_and_original_spell_lki_is_copied(cards, remove_original):
    s = table(cards, [NAME, 'Counterspell'], ['Lightning Bolt'])
    source = put(s, NAME, 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    act(s, 'p2', type='set_prefs', hold_priority=True)
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    if remove_original:
        wait_priority(s, 'p1')
        counter = put(s, 'Counterspell', 'hand')
        mana(s, U=2)
        act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[bolt.id])
    d = until_asked(s)
    # With no mana the opponent cannot pay; only the controller's optional copy remains.
    assert d.player == 'p1' and d.resume['step'] == 'pay_or_sacrifice'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    d = s.state.rules.decision
    assert d.resume['step'] == 'copy_target'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['keep'])
    settle(s)
    assert s.state.players['p3'].life == (37 if remove_original else 34)
    roundtrip(s)


def test_front_opponent_can_activate_mana_ability_during_payment(cards):
    s = table(cards, [NAME], ['Lightning Bolt', 'Sol Ring'])
    put(s, NAME, 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    ring = put(s, 'Sol Ring', 'battlefield', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    d = until_asked(s)
    assert d.player == 'p2'
    act(s, 'p2', type='activate_ability', card_id=ring.id, ability=0)
    roundtrip(s)
    d = s.state.rules.decision
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    assert s.state.cards[ring.id].tapped
    assert s.state.players['p3'].life == 37
    assert not any(s.state.players['p2'].mana.values())
    roundtrip(s)


def test_front_trigger_controller_is_fixed_when_source_changes_controller(cards):
    s = table(cards, [NAME], ['Lightning Bolt'])
    source = put(s, NAME, 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    act(s, 'p2', type='set_prefs', hold_priority=True)
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    d = until_asked(s)
    assert d.player == 'p1' and d.resume['step'] == 'pay_or_sacrifice'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert s.state.players['p3'].life == 37
    roundtrip(s)


def test_explore_short_library_and_foreign_card_rejection(cards):
    s = table(cards, [NAME], ['Lightning Bolt'])
    source = put(s, NAME, 'hand')
    for p in ['p1', 'p2', 'p3']:
        ids = list(s.state.zones[f'{p}:library'])
        act(s, 'p1', type='move', card_ids=ids[1:], to={'player': p, 'zone': 'hand'})
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
    d = until_asked(s)
    theirs = s.state.zones['p2:library'][0]
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[theirs])
    for p in ['p1', 'p2', 'p3']:
        d = s.state.rules.decision
        assert d.player == p and d.max_choices == 1
        act(s, p, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert all(not s.state.zones[f'{p}:library'] for p in ['p1', 'p2', 'p3'])
    assert all(p.life == 43 for p in s.state.players.values())
    roundtrip(s)
