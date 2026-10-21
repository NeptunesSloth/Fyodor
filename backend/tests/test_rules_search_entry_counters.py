"""CR 122.6: a searched creature enters with the instructed additional counter."""
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

NAME = 'Neoform'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/search_entry_counter_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, [NAME, 'Grizzly Bears', 'Centaur Courser', 'Doubling Season', 'Solemnity', 'Containment Priest'], [])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell = put(s, NAME, 'hand')
    mana(s, G=1, U=1)
    return s, bear, spell


def cast(s, bear, spell):
    act(s, 'p1', type='cast_spell', card_id=spell.id,
        cost_choices=[{'component': 0, 'cards': [bear.id]}])
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_exact_sacrificed_mana_value_plus_one_enters_with_counter(cards):
    s, bear, spell = setup(cards)
    cast(s, bear, spell)
    d = s.state.rules.decision
    assert d is not None and d.kind == 'choose_cards' and d.resume.get('step') == 'search'
    found = next(c for c in s.state.cards.values() if c.name == 'Centaur Courser')
    assert found.id in {o.id for o in d.options}
    assert bear.id not in {o.id for o in d.options}
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[found.id])
    settle(s)
    assert s.state.cards[found.id].zone == 'p1:battlefield'
    assert s.state.cards[found.id].counters.get('+1/+1') == 1
    roundtrip(s)


def test_qualified_search_can_fail_without_refunding_sacrifice(cards):
    s, bear, spell = setup(cards)
    cast(s, bear, spell)
    d = s.state.rules.decision
    assert d is not None and d.kind == 'choose_cards' and d.resume.get('step') == 'search'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert not any(c.name == 'Centaur Courser' and c.zone.endswith(':battlefield') for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize('permanent,counters,zone', [
    ('Doubling Season', 2, 'battlefield'),
    ('Solemnity', 0, 'battlefield'),
    ('Containment Priest', 0, 'exile'),
])
def test_counter_and_entry_replacements_apply_to_the_search_instruction(cards, permanent, counters, zone):
    s, bear, spell = setup(cards)
    put(s, permanent, 'battlefield')
    settle(s)
    cast(s, bear, spell)
    d = s.state.rules.decision
    assert d is not None and d.resume.get('step') == 'search'
    found = next(c for c in s.state.cards.values() if c.name == 'Centaur Courser')
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[found.id])
    settle(s)
    assert s.state.cards[found.id].zone == f'p1:{zone}'
    assert s.state.cards[found.id].counters.get('+1/+1', 0) == counters
    roundtrip(s)
