"""CR 111.2, 608.2h: conditional attached copy and actual creation fallback."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/attached_basic_land_types_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAME = "Nylea's Presence"
BASICS = {'Plains', 'Island', 'Swamp', 'Mountain', 'Forest'}


def setup(cards, land='Darksteel Citadel'):
    s = table(cards, [NAME, land, 'Demystify', 'Blood Moon', 'Phantasmal Terrain', 'Emeria Shepherd', 'Grizzly Bears'])
    host = put(s, land, 'battlefield')
    aura = put(s, NAME, 'hand')
    mana(s, C=1, G=1)
    before = len(s.state.zones.get('p1:hand', []))
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[host.id])
    settle(s)
    assert len(s.state.zones.get('p1:hand', [])) == before  # Aura cast (-1), its ETB draw (+1).
    return s, aura, host


def test_canonical_nylea_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_adding_basic_types_preserves_artifact_indestructible_and_original_mana(cards):
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, _, host = setup(cards)
    ch = chars(s, host)
    assert ch.types == {'Artifact', 'Land'} and ch.subtypes >= BASICS
    assert 'indestructible' in ch.keywords
    texts = {a.text for a in ch.abilities}
    assert all(f'{{T}}: Add {{{c}}}.' in texts for c in 'CWUBRG')
    roundtrip(s)


@pytest.mark.parametrize('color', list('WUBRG'))
def test_each_intrinsic_mana_ability_works(cards, color):
    from tests.game_helpers import mana_pool
    from tests.test_rules_wave7b_activation import ability_index

    s, _, host = setup(cards)
    act(s, 'p1', type='activate_ability', card_id=host.id, ability=ability_index(s, host, f'Add {{{color}}}'))
    assert mana_pool(s) == {color: 1} and s.state.cards[host.id].tapped
    roundtrip(s)


def test_nonbasic_urza_subtypes_and_original_mana_survive(cards):
    from tests.game_helpers import mana_pool
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave7b_activation import ability_index

    s, _, host = setup(cards, "Urza's Tower")
    assert chars(s, host).subtypes == BASICS | {"Urza's", 'Tower'}
    act(s, 'p1', type='activate_ability', card_id=host.id, ability=ability_index(s, host, 'Add {C}'))
    assert mana_pool(s) == {'C': 1}
    roundtrip(s)


def test_aura_removal_removes_gained_types_and_mana_only(cards):
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, aura, host = setup(cards)
    spell = put(s, 'Demystify', 'hand')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[aura.id])
    settle(s)
    ch = chars(s, host)
    assert ch.subtypes == set() and ch.types == {'Artifact', 'Land'}
    assert 'indestructible' in ch.keywords
    assert [a.text for a in ch.abilities if a.kind == 'mana'] == ['{T}: Add {C}.']
    roundtrip(s)


@pytest.mark.parametrize('moon_first', [False, True])
def test_timestamp_order_with_blood_moon_preserves_305_7_ability_loss(cards, moon_first):
    from tests.test_rules_wave6c_tokens_pumps import chars

    s = table(cards, [NAME, 'Darksteel Citadel', 'Blood Moon'])
    if moon_first:
        put(s, 'Blood Moon', 'battlefield')
    host = put(s, 'Darksteel Citadel', 'battlefield')
    aura = put(s, NAME, 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[host.id])
    settle(s)
    if not moon_first:
        put(s, 'Blood Moon', 'battlefield')
    ch = chars(s, host)
    assert ch.subtypes == (BASICS if moon_first else {'Mountain'})
    assert 'indestructible' not in ch.keywords
    assert '{T}: Add {C}.' not in {a.text for a in ch.abilities}
    roundtrip(s)


def test_host_control_change_keeps_attached_land_types(cards):
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, _, host = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[host.id], player='p2')
    assert chars(s, host).subtypes >= BASICS
    roundtrip(s)


def test_adding_basic_land_types_does_not_trigger_landfall(cards):
    s = table(cards, [NAME, 'Darksteel Citadel', 'Emeria Shepherd', 'Grizzly Bears'])
    source = put(s, 'Emeria Shepherd', 'battlefield')
    target = put(s, 'Grizzly Bears', 'graveyard')
    land = put(s, 'Darksteel Citadel', 'hand')
    act(s, 'p1', type='play_land', card_id=land.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and target.id in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'hand', 'decline'}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    aura = put(s, NAME, 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[land.id])
    settle(s)
    from tests.test_rules_wave6c_tokens_pumps import chars

    assert 'Plains' in chars(s, land).subtypes
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    roundtrip(s)
