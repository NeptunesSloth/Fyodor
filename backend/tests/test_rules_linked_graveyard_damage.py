"""CR 608.2d, 701.13, 202.3: opponent choices and milled-card mana values."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/linked_graveyard_damage_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Valakut Exploration')).level == 'FULL'


def setup(cards, names=('Sol Ring', 'Grizzly Bears', 'Lightning Bolt'), *, controller='p1'):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Valakut Exploration', 'Rest in Peace', 'Solitary Confinement', 'Azusa, Lost but Seeking', 'Mountain', 'Mountain', 'Mountain', *names],
              ['Valakut Exploration', 'Solitary Confinement', *names], [])
    to_phase(s, 'main1')
    source = put(s, 'Valakut Exploration', 'battlefield', controller)
    chosen = []
    for name in names:
        chosen.append(next(c.id for c in s.state.cards.values() if c.owner == controller and c.name == name and c.id not in chosen))
    if chosen:
        act(s, controller, type='move', card_ids=chosen, to={'player': controller, 'zone': 'library'}, index=0)
    put(s, 'Azusa, Lost but Seeking', 'battlefield')
    lands = [c.id for c in s.state.cards.values() if c.owner == controller and c.name == 'Mountain']
    for cid in lands[:len(names)]:
        act(s, controller, type='move', card_ids=[cid], to={'player': controller, 'zone': 'hand'})
        act(s, controller, type='play_land', card_id=cid)
        settle(s)
    assert all(s.state.cards[c].zone == controller+':exile' for c in chosen)
    return s, source, chosen


def end(s):
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'end')
    roundtrip(s)
    settle(s)
    roundtrip(s)


def test_linked_cards_move_to_graveyard_and_damage_each_opponent(cards):
    s, _, chosen = setup(cards)
    end(s)
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in chosen)
    assert [s.state.players[p].life for p in ['p1', 'p2', 'p3']] == [40, 37, 37]


def test_no_linked_cards_means_no_end_step_trigger(cards):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase
    s, _, _ = setup(cards, names=())
    to_phase(s, 'end')
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_graveyard_replacement_contributes_no_damage(cards):
    from tests.test_rules_designations import put
    s, _, chosen = setup(cards)
    put(s, 'Rest in Peace', 'battlefield')
    end(s)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in chosen)
    assert all(p.life == 40 for p in s.state.players.values())


def test_damage_uses_ability_controller_and_can_be_prevented(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_wave30m_durations import to_phase
    s, source, _ = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    put(s, 'Solitary Confinement', 'battlefield')
    to_phase(s, 'end', turn=2)
    end(s)
    assert [s.state.players[p].life for p in ['p1', 'p2', 'p3']] == [40, 40, 37]


@pytest.mark.parametrize('blink', [False, True])
def test_departure_before_end_step_leaves_old_cards_playable_without_cleanup(cards, blink):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    s, source, chosen = setup(cards)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    if blink:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    end(s)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in chosen)
    assert all(p.life == 40 for p in s.state.players.values())
    # Granted permissions are independent of whether the enchantment remains.
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'main1', turn=4)
    mana(s, C=1)
    act(s, 'p1', type='cast_spell', card_id=chosen[0])
    from tests.test_rules_designations import settle
    settle(s)
    assert s.state.cards[chosen[0]].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('blink', [False, True])
def test_departure_after_trigger_uses_old_linked_set(cards, blink):
    from tests.game_helpers import act
    from tests.test_rules_wave30m_durations import to_phase
    s, source, chosen = setup(cards)
    to_phase(s, 'end')
    assert s.state.zones['stack']
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    if blink:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    end(s)
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in chosen)
    assert s.state.players['p2'].life == 37


def test_spell_played_from_exile_before_end_step_is_not_counted(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import settle
    s, _, chosen = setup(cards)
    mana(s, C=1)
    act(s, 'p1', type='cast_spell', card_id=chosen[0])
    settle(s)
    end(s)
    assert s.state.cards[chosen[0]].zone == 'p1:battlefield'
    assert s.state.players['p2'].life == 38


def test_spell_played_in_response_to_end_step_is_not_counted(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_wave30m_durations import to_phase
    s, _, chosen = setup(cards)
    to_phase(s, 'end')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=chosen[2], targets=['p2'])
    end(s)
    assert s.state.players['p2'].life == 35
    assert s.state.players['p3'].life == 38


def test_intervening_condition_rechecked_when_all_linked_cards_leave(cards):
    from tests.game_helpers import act
    from tests.test_rules_wave30m_durations import to_phase
    s, _, chosen = setup(cards)
    to_phase(s, 'end')
    act(s, 'p1', type='move', card_ids=chosen, to={'player': 'p1', 'zone': 'hand'})
    end(s)
    assert all(p.life == 40 for p in s.state.players.values())


def test_exile_leave_and_return_is_a_new_unlinked_object(cards):
    from tests.game_helpers import act
    s, _, chosen = setup(cards)
    act(s, 'p1', type='move', card_ids=[chosen[0]], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[chosen[0]], to={'player': 'p1', 'zone': 'exile'})
    end(s)
    assert s.state.cards[chosen[0]].zone == 'p1:exile'
    assert s.state.players['p2'].life == 38


def test_one_linked_set_can_hold_cards_owned_by_different_players(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave30m_durations import to_phase

    s, source, chosen = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    to_phase(s, 'main1', turn=2)
    other = put(s, 'Sol Ring', 'library', 'p2')
    act(s, 'p2', type='move', card_ids=[other.id], to={'player': 'p2', 'zone': 'library'}, index=0)
    land = put(s, 'Island', 'hand', 'p2')
    act(s, 'p2', type='play_land', card_id=land.id)
    settle(s)
    assert s.state.cards[other.id].zone == 'p2:exile'
    end(s)
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in chosen)
    assert s.state.cards[other.id].zone == 'p2:graveyard'
    assert [s.state.players[p].life for p in ['p1', 'p2', 'p3']] == [36, 40, 36]
    roundtrip(s)
