"""Supported command-zone static rules remain live after their planeswalker leaves."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import to_phase

TEFERI = 'Teferi, Temporal Archmage'
SAHEELI = 'Saheeli, Filigree Master'
NARSET = 'Narset Transcendent'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/command_static_emblem_cards.json').read_text())
    for i, c in enumerate(rows):
        base[c['name']] = card(c['name'], set_code='cse', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name=TEFERI):
    s = table(cards, [name, 'Jace Beleren', 'Sol Ring', 'Myr Retriever', 'Grizzly Bears', 'Sarkhan the Masterless'],
              ['Jace Beleren', 'Lightning Bolt', 'Sol Ring', 'Grizzly Bears', 'Balmor, Battlemage Captain'])
    ultimate(s, name)
    return s


def ultimate(s, name):
    source = put(s, name, 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value={TEFERI: 10, SAHEELI: 4, NARSET: 9}[name])
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'You get an emblem'))
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def activate_jace(s, jace, pid='p1'):
    wait_priority(s, pid)
    act(s, pid, type='activate_ability', card_id=jace.id, ability=0)


def put_jace(s):
    jace = put(s, 'Jace Beleren', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=jace.id, kind='loyalty', value=3)
    return jace


@pytest.mark.parametrize('name', [TEFERI, SAHEELI, NARSET])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_teferi_allows_loyalty_on_opponent_turn_but_only_once_that_turn(cards):
    s = setup(cards)
    jace = put_jace(s)
    to_phase(s, 'main1', turn=2)
    before = len(s.state.zones['p1:hand'])
    activate_jace(s, jace)
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    with pytest.raises(ActionError):
        activate_jace(s, jace)
    to_phase(s, 'main1', turn=3)
    activate_jace(s, jace)
    settle(s)
    assert s.state.cards[jace.id].counters['loyalty'] == 7
    roundtrip(s)


def test_teferi_allows_responding_to_a_spell_with_a_loyalty_ability(cards):
    s = setup(cards)
    jace = put_jace(s)
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p1'])
    activate_jace(s, jace)
    assert len(s.state.zones['stack']) == 2
    settle(s)
    assert s.state.players['p1'].life == 37
    roundtrip(s)


def test_teferi_grant_tracks_current_controller_and_does_not_help_opponents(cards):
    s = setup(cards)
    jace = put_jace(s)
    act(s, 'p1', type='set_controller', card_ids=[jace.id], player='p2')
    to_phase(s, 'main1', turn=3)
    with pytest.raises(ActionError):
        activate_jace(s, jace, pid='p2')
    act(s, 'p1', type='set_controller', card_ids=[jace.id], player='p1')
    activate_jace(s, jace)
    settle(s)
    roundtrip(s)


def test_multiple_teferi_emblems_do_not_add_loyalty_activations(cards):
    s = setup(cards)
    ultimate(s, TEFERI)
    jace = put_jace(s)
    to_phase(s, 'main1', turn=2)
    activate_jace(s, jace)
    settle(s)
    with pytest.raises(ActionError):
        activate_jace(s, jace)
    roundtrip(s)


def test_planeswalker_animated_by_sarkhan_does_not_receive_emblem_timing_exception(cards):
    s = setup(cards)
    jace = put_jace(s)
    sarkhan = put(s, 'Sarkhan the Masterless', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=sarkhan.id, kind='loyalty', value=5)
    act(s, 'p1', type='activate_ability', card_id=sarkhan.id, ability=1)
    settle(s)
    assert 'Planeswalker' not in Plan(s.state, 'p1', cards, None).ch(s.state.cards[jace.id]).types
    ring = put(s, 'Sol Ring', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='cast_spell', card_id=ring.id)
    assert ring.id in s.state.zones['stack']
    with pytest.raises(ActionError):
        activate_jace(s, jace)
    settle(s)
    roundtrip(s)


def test_saheeli_emblem_pumps_artifact_creatures_and_reduces_only_artifact_spells(cards):
    s = setup(cards, SAHEELI)
    myr = put(s, 'Myr Retriever', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    plan = Plan(s.state, 'p1', cards, None)
    assert plan.ch(myr).pt == (2, 2)
    assert plan.ch(bear).pt == (2, 2)
    ring = put(s, 'Sol Ring', 'hand')
    act(s, 'p1', type='cast_spell', card_id=ring.id)
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:battlefield' and mana_pool(s, 'p1') == {}
    bear = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bear.id, sources=[])
    roundtrip(s)


def test_narset_emblem_stops_opponent_noncreatures_but_allows_creatures(cards):
    s = setup(cards, NARSET)
    to_phase(s, 'main1', turn=2)
    ring = put(s, 'Sol Ring', 'hand', pid='p2')
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2, 'R': 1, 'G': 1})
    for source, targets in [(ring, []), (bolt, ['p1'])]:
        with pytest.raises(ActionError):
            act(s, 'p2', type='cast_spell', card_id=source.id, targets=targets)
    bear = put(s, 'Grizzly Bears', 'hand', pid='p2')
    act(s, 'p2', type='cast_spell', card_id=bear.id)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:battlefield'
    roundtrip(s)
