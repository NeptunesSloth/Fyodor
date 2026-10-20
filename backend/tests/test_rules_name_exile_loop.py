"""CR 201.2: choices in a name-sensitive exile loop."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/name_exile_loop_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_tainted_pact_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Tainted Pact')).level == 'FULL'


def setup_library(cards, names):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Tainted Pact', *names], [], [])
    source = put(s, 'Tainted Pact', 'hand')
    chosen = []
    for name in names:
        chosen.append(next(c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == name and c.id not in chosen))
    if s.state.zones.get('p1:library'):
        act(s, 'p1', type='move', card_ids=list(s.state.zones['p1:library']), to={'player': 'p1', 'zone': 'exile'})
    if chosen:
        act(s, 'p1', type='move', card_ids=chosen, to={'player': 'p1', 'zone': 'library'}, index=0)
    assert s.state.zones.get('p1:library', []) == chosen
    mana(s, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    return s, source, chosen


def answer(s, option):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    d = s.state.rules.decision
    assert d and d.resume['step'] == 'name_exile_loop'
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])
    settle(s)


@pytest.mark.parametrize('take_at', [0, 1, 2])
def test_can_take_first_or_later_unique_card_and_leaves_rest_of_library(cards, take_at):
    from tests.test_rules_designations import roundtrip

    s, source, chosen = setup_library(cards, ['Grizzly Bears', 'Sol Ring', 'Island', 'Forest'])
    for _ in range(take_at):
        answer(s, 'continue')
    d = s.state.rules.decision
    assert d and d.options[0].card_id == chosen[take_at]
    answer(s, 'take')
    assert s.state.rules.decision is None
    assert s.state.cards[chosen[take_at]].zone == 'p1:hand'
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in chosen[:take_at])
    assert s.state.zones['p1:library'] == chosen[take_at + 1:]
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('names', [ ['Grizzly Bears', 'Sol Ring', 'Grizzly Bears', 'Forest'],
                                  ['Fire // Ice', 'Sol Ring', 'Start // Fire', 'Forest'] ])
def test_duplicate_name_including_shared_split_half_stops_without_hand_choice(cards, names):
    from tests.test_rules_designations import roundtrip

    s, _, chosen = setup_library(cards, names)
    answer(s, 'continue')
    answer(s, 'continue')
    assert s.state.rules.decision is None
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in chosen[:3])
    assert s.state.zones['p1:library'] == chosen[3:]
    roundtrip(s)


def test_empty_library_finishes_without_drawing_or_losing(cards):
    from tests.test_rules_designations import roundtrip

    s, source, _ = setup_library(cards, [])
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert 'p1' not in s.state.rules.lost
    roundtrip(s)


def test_can_decline_every_unique_card_and_exhaust_library_without_drawing(cards):
    from tests.test_rules_designations import roundtrip

    s, _, chosen = setup_library(cards, ['Grizzly Bears', 'Sol Ring', 'Island'])
    for _ in chosen:
        answer(s, 'continue')
    assert s.state.rules.decision is None
    assert not s.state.zones['p1:library']
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in chosen)
    assert 'p1' not in s.state.rules.lost
    roundtrip(s)


def test_only_exiled_card_becomes_public_and_future_library_card_stays_hidden(cards):
    from tests.test_rules_designations import roundtrip

    s, _, chosen = setup_library(cards, ['Grizzly Bears', 'Sol Ring'])
    for pid in ['p2', 'p3']:
        names = [c.get('name') for c in s.view(pid)['cards'].values()]
        assert 'Grizzly Bears' in names
        assert 'Sol Ring' not in names
    assert s.state.cards[chosen[1]].zone == 'p1:library'
    answer(s, 'take')
    assert s.state.zones['p1:library'] == chosen[1:]
    roundtrip(s)
