"""CR 702.43a, 702.44c: modular with a sunburst entry count."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/modular_sunburst_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Arcbound Wanderer'


def test_wanderer_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, *, doubling=False, solemnity=False):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Ornithopter', 'Sol Ring', 'Grizzly Bears', 'Murder', 'Reanimate',
                      'Vorinclex, Monstrous Raider', 'Solemnity'], [])
    recipient = put(s, 'Ornithopter', 'battlefield')
    source = put(s, NAME, 'hand')
    if doubling:
        put(s, 'Vorinclex, Monstrous Raider', 'battlefield')
    if solemnity:
        put(s, 'Solemnity', 'battlefield')
    return s, source, recipient


@pytest.mark.parametrize('payment,count', [({'C': 6}, 0), ({'R': 6}, 1),
                                          ({'C': 4, 'W': 1, 'U': 1}, 2),
                                          ({'C': 1, 'W': 1, 'U': 1, 'B': 1, 'R': 1, 'G': 1}, 5)])
def test_entry_counts_distinct_spent_colors(cards, payment, count):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, source, recipient = setup(cards)
    mana(s, **payment)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone == ('p1:battlefield' if count else 'p1:graveyard')
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == count
    assert not s.state.cards[recipient.id].counters
    roundtrip(s)


@pytest.mark.parametrize('doubling', [False, True])
def test_death_transfers_actual_counters_and_counter_replacements(cards, doubling):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, source, recipient = setup(cards, doubling=doubling)
    put(s, 'Sol Ring', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield')
    mana(s, C=4, W=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].counters['+1/+1'] == (4 if doubling else 2)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='+1/+1', value=5)
    wait_priority(s, 'p1')
    spell = put(s, 'Murder', 'hand')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[recipient.id].counters['+1/+1'] == (10 if doubling else 5)
    roundtrip(s)


def test_solemnity_prevents_entry_counters(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, source, recipient = setup(cards, solemnity=True)
    mana(s, C=1, W=1, U=1, B=1, R=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert not s.state.cards[recipient.id].counters
    roundtrip(s)


def test_reanimated_wanderer_has_no_cast_colors(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, source, recipient = setup(cards)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    spell = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    life = s.state.players['p1'].life
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].life == life - 6
    assert not s.state.cards[recipient.id].counters
    roundtrip(s)
