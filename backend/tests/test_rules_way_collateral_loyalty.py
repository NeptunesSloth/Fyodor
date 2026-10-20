"""Exact Oracle collateral: legendary empower enchantments grant controlled planeswalkers loyalty abilities."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Way of the Pyromancer', 'Way of the Cryomancer', 'Way of the Healer']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/way_collateral_loyalty_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='wcl', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name):
    s = table(cards, [name, 'Grizzly Bears', 'Lightning Bolt', 'Lightning Bolt', 'Jace Beleren'], ['Jace Beleren'], [])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=4)
    source = put(s, name, 'hand')
    due = {NAMES[0]: {'C': 1, 'R': 1}, NAMES[1]: {'C': 2, 'U': 1}, NAMES[2]: {'C': 3, 'W': 1}}[name]
    mana(s, **due)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    jaces = [c for c in s.state.cards.values() if c.name == 'Jace' and c.is_token and c.zone == 'p1:battlefield']
    assert len(jaces) == 1
    return s, s.state.cards[source.id], jaces[0], bear


def activate(s, jace, needle):
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=jace.id, ability=ability_index(s, s.state.cards[jace.id], needle))


@pytest.mark.parametrize('name', NAMES)
def test_exact_way_is_full_and_native_cast_empowers_jace(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'
    s, source, jace, bear = setup(cards, name)
    assert jace.counters['loyalty'] == (2 if name == NAMES[0] else 5)
    plan = Plan(s.state, 'p1', s.cards, None)
    assert plan.ch(source).types == frozenset({'Enchantment'})
    assert 'Aura' not in plan.ch(source).subtypes
    assert 'Planeswalker' in plan.ch(jace).types
    assert not any(d.get('loyalty') for d in scripts.definitions(plan.ch(s.state.cards[bear.id])).values())
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_pyromancer_is_a_normal_loyalty_ability_not_an_immediate_mana_ability(cards):
    s, source, jace, _ = setup(cards, NAMES[0])
    activate(s, jace, 'Add')
    assert s.state.cards[jace.id].counters['loyalty'] == 3
    assert not mana_pool(s).get('R', 0)
    assert s.state.zones.get('stack')
    # The already activated ability survives losing its static grant.
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert mana_pool(s).get('R') == 1
    with pytest.raises(ActionError):
        activate(s, jace, 'Surveil')
    roundtrip(s)


@pytest.mark.parametrize('name,needle', [(NAMES[0], 'Add'), (NAMES[1], 'next cast'), (NAMES[2], 'Cadet')])
def test_granted_loyalty_obeys_main_phase_empty_stack_and_one_per_turn(cards, name, needle):
    s, _, jace, _ = setup(cards, name)
    to_phase(s, 'begin_combat', turn=4)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        activate(s, jace, needle)
    assert s.state.model_dump(mode='json') == before
    to_phase(s, 'main2', turn=4)
    activate(s, jace, needle)
    settle(s)
    with pytest.raises(ActionError):
        activate(s, jace, 'Surveil')
    roundtrip(s)


def test_healer_zero_loyalty_jace_dies_but_creates_cadet_and_surveils(cards):
    s, _, jace, bear = setup(cards, NAMES[2])
    act(s, 'p1', type='set_counter', card_id=jace.id, kind='loyalty', value=2)
    top = s.state.zones['p1:library'][0]
    activate(s, jace, 'Cadet')
    assert jace.id not in s.state.cards
    settle(s)
    cadets = [c for c in s.state.cards.values() if c.is_token and c.name == 'Cadet' and c.zone == 'p1:battlefield']
    assert len(cadets) == 1
    assert Plan(s.state, 'p1', s.cards, None).ch(cadets[0]).pt == (2, 2)
    assert s.state.cards[top].zone == 'p1:graveyard'
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_cryomancer_next_spell_copy_survives_enchantment_departure_and_is_once(cards):
    s, source, jace, _ = setup(cards, NAMES[1])
    activate(s, jace, 'next cast')
    settle(s)
    assert s.state.cards[jace.id].counters['loyalty'] == 2
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    spent = []
    for expected in [34, 31]:
        bolt = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Lightning Bolt' and c.id not in spent)
        spent.append(bolt.id)
        act(s, 'p1', type='move', card_ids=[bolt.id], to={'player': 'p1', 'zone': 'hand'})
        wait_priority(s, 'p1')
        mana(s, R=1)
        act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
        settle(s)
        assert s.state.players['p2'].life == expected
    roundtrip(s)


def test_grants_apply_to_other_controlled_planeswalkers_only_and_end_with_source(cards):
    s, source, _, bear = setup(cards, NAMES[0])
    own = put(s, 'Jace Beleren', 'battlefield')
    enemy = put(s, 'Jace Beleren', 'battlefield', 'p2')
    for c in [own, enemy]:
        act(s, c.owner, type='set_counter', card_id=c.id, kind='loyalty', value=3)
    def texts(c):
        return [a.text for a in Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[c.id]).abilities]
    assert any('Add {R}' in t for t in texts(own))
    assert not any('Add {R}' in t for t in texts(enemy))
    assert not any('Add {R}' in t for t in texts(bear))
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert not any('Add {R}' in t for t in texts(own))
    assert s.state.cards[own.id].counters['loyalty'] == 3
    roundtrip(s)
