"""CR 122.6: a privately selected creature enters with conditional additional counters."""
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
from tests.test_rules_abundance import set_library
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = 'Turntimber Symbiosis // Turntimber, Serpentine Wood'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/turntimber_symbiosis_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def setup(cards, selected='Grizzly Bears', permanent=None, top_names=None):
    s = table(cards, [NAME, 'Grizzly Bears', 'Centaur Courser', 'Ravenous Chupacabra', 'Walking Ballista',
                      'Doubling Season', 'Solemnity', 'Containment Priest', "Grafdigger's Cage", 'Forest', 'Island'], ['Grizzly Bears'])
    spell = put(s, NAME, 'hand')
    if permanent:
        put(s, permanent, 'battlefield')
    top = set_library(s, top_names or [selected, 'Forest', 'Island'])
    mana(s, C=4, G=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume.get('step') == 'pick_looked'
    assert d.player == 'p1' and d.min_choices == 0
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    assert all(not s.view('p2')['cards'].get(cid, {}).get('name') for cid in top)
    roundtrip(s)
    return s, top, d


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('name,n', [('Grizzly Bears', 3), ('Centaur Courser', 3), ('Walking Ballista', 3)])
def test_small_creature_enters_with_counters_before_state_actions(cards, name, n):
    s, top, d = setup(cards, name)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
    settle(s)
    c = s.state.cards[top[0]]
    assert c.zone == 'p1:battlefield' and c.counters.get('+1/+1') == n
    assert set(s.state.zones['p1:library']) == set(top[1:])
    roundtrip(s)


@pytest.mark.parametrize('permanent,n,zone', [('Doubling Season', 6, 'battlefield'), ('Solemnity', 0, 'battlefield'),
                                             ('Containment Priest', 0, 'exile'), ("Grafdigger's Cage", 0, 'library')])
def test_entry_replacement_and_prohibition(cards, permanent, n, zone):
    s, top, d = setup(cards, permanent=permanent)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
    settle(s)
    c = s.state.cards[top[0]]
    assert c.zone == f'p1:{zone}' and c.counters.get('+1/+1', 0) == n
    if zone == 'library':
        assert s.state.zones['p1:library'][0] == top[0]
    roundtrip(s)


@pytest.mark.parametrize('name', ['Grizzly Bears', 'Forest'])
def test_decline_and_no_creatures_remain_private_optional_choices(cards, name):
    s, top, d = setup(cards, name)
    assert len(d.options) == (1 if name == 'Grizzly Bears' else 0)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert set(s.state.zones['p1:library']) == set(top)
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_back_land_face_actual_play_and_mana(cards, pay):
    from tests.game_helpers import mana_pool

    s = table(cards, [NAME], [])
    spell = put(s, NAME, 'hand')
    act(s, 'p1', type='play_land', card_id=spell.id, face=1, pay_life=pay)
    assert s.state.cards[spell.id].face == 1 and s.state.cards[spell.id].tapped != pay
    assert s.state.players['p1'].life == 40 - (3 if pay else 0)
    if pay:
        act(s, 'p1', type='activate_ability', card_id=spell.id, ability=1)
        assert mana_pool(s) == {'G': 1}
    roundtrip(s)


def test_large_creature_no_counters_and_actual_etb(cards):
    s, top, d = setup(cards, 'Ravenous Chupacabra')
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
    settle(s)
    c = s.state.cards[top[0]]
    assert c.zone == 'p1:battlefield' and not c.counters
    d = s.state.rules.decision
    assert d is not None and victim.id in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_exactly_seven_looked_and_unlooked_tail_stays_above_bottomed_rest(cards):
    names = ['Grizzly Bears', 'Centaur Courser', 'Walking Ballista', 'Forest', 'Island',
             'Doubling Season', 'Solemnity', 'Ravenous Chupacabra']
    s, top, d = setup(cards, top_names=names)
    assert {o.id for o in d.options} == set(top[:3])
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
    settle(s)
    assert s.state.zones['p1:library'][0] == top[-1]
    assert set(s.state.zones['p1:library'][1:]) == set(top[1:7])
    roundtrip(s)
