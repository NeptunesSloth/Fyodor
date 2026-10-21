"""CR 205.3i, 305.6: every nonbasic land subtype."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import mana_pool


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/nonbasic_land_types_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_nexus_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Planar Nexus')).level == 'FULL'


def test_has_every_nonbasic_type_in_every_zone_and_no_basic_mana(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave6c_tokens_pumps import chars

    s = table(cards, ['Planar Nexus'], [])
    nexus = put(s, 'Planar Nexus', 'hand')
    assert {'Locus', 'Gate', 'Mine', 'Tower'} <= chars(s, nexus).subtypes
    act(s, 'p1', type='play_land', card_id=nexus.id)
    ch = chars(s, nexus)
    assert {'Cave', 'Desert', 'Gate', 'Lair', 'Locus', 'Mine', 'Planet', 'Power-Plant', 'Sphere', 'Tower', 'Town', "Urza's"} <= ch.subtypes
    assert not {'Plains', 'Island', 'Swamp', 'Mountain', 'Forest'} & ch.subtypes
    assert 'Basic' not in ch.supertypes
    assert len([a for a in ch.abilities if a.kind == 'mana']) == 2
    act(s, 'p1', type='move', card_ids=[nexus.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert {'Locus', 'Gate', 'Mine', 'Tower'} <= chars(s, nexus).subtypes
    roundtrip(s)


def test_nexus_supplies_both_missing_urza_types(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Planar Nexus', "Urza's Tower"], [])
    nexus = put(s, 'Planar Nexus', 'battlefield')
    tower = put(s, "Urza's Tower", 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=tower.id, ability=ability_index(s, tower, 'Add {C}'))
    assert mana_pool(s) == {'C': 3}
    assert not s.state.cards[nexus.id].tapped
    roundtrip(s)


def test_opponents_nexus_counts_as_a_locus(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Cloudpost'], ['Planar Nexus'])
    cloud = put(s, 'Cloudpost', 'battlefield')
    put(s, 'Planar Nexus', 'battlefield', 'p2')
    act(s, 'p1', type='activate_ability', card_id=cloud.id, ability=ability_index(s, cloud, 'Add {C}'))
    assert mana_pool(s) == {'C': 2}
    roundtrip(s)


@pytest.mark.parametrize('moon_first', [True, False])
def test_blood_moon_overrides_nexus_regardless_of_timestamp(cards, moon_first):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave6c_tokens_pumps import chars

    s = table(cards, ['Planar Nexus', 'Blood Moon'], [])
    if moon_first:
        moon = put(s, 'Blood Moon', 'battlefield')
    nexus = put(s, 'Planar Nexus', 'battlefield')
    if not moon_first:
        moon = put(s, 'Blood Moon', 'battlefield')
    assert chars(s, nexus).subtypes == {'Mountain'}
    act(s, 'p1', type='move', card_ids=[moon.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert 'Locus' in chars(s, nexus).subtypes and 'Mountain' not in chars(s, nexus).subtypes
    roundtrip(s)


def test_adding_a_basic_land_type_retains_nexus_types_and_gains_mana(cards):
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave6c_tokens_pumps import chars

    s = table(cards, ['Planar Nexus', 'Yavimaya, Cradle of Growth'], [])
    nexus = put(s, 'Planar Nexus', 'battlefield')
    put(s, 'Yavimaya, Cradle of Growth', 'battlefield')
    ch = chars(s, nexus)
    assert {'Forest', 'Locus', 'Gate', 'Tower'} <= ch.subtypes
    assert 'Basic' not in ch.supertypes
    assert any(a.intrinsic and a.text == '{T}: Add {G}.' for a in ch.abilities)
    roundtrip(s)


def test_gate_search_finds_nexus_in_library(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Planar Nexus', 'Circuitous Route'], [])
    nexus = put(s, 'Planar Nexus', 'library')
    spell = put(s, 'Circuitous Route', 'hand')
    mana(s, G=4)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    d = s.state.rules.decision
    assert d and any(o.card_id == nexus.id for o in d.options)
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == nexus.id)])
    settle(s)
    assert s.state.cards[nexus.id].zone == 'p1:battlefield' and s.state.cards[nexus.id].tapped
    roundtrip(s)
