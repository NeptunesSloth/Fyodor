"""A reflexive counter threshold gates triggering and the entire resolving ability."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = 'Earthbender Ascension'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/reflexive_counter_threshold_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='rct', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, quests=3, replacement=None):
    s = table(cards, [NAME, 'Forest', 'Grizzly Bears', 'Solemnity', 'Doubling Season', 'Stifle'], ['Vampire Hexmage'])
    source = put(s, NAME, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    if replacement:
        put(s, replacement, 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='quest', value=quests)
    land = put(s, 'Forest', 'hand')
    act(s, 'p1', type='play_land', card_id=land.id)
    settle(s)
    roundtrip(s)
    return s, source, bear


def choose_bear(s, bear):
    d = s.state.rules.decision
    assert d is not None and any(o.id == bear.id for o in d.options)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])


def has_trample(s, cards, bear):
    return 'trample' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).keywords


def test_canonical_card_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('quests', [0, 2])
def test_quest_below_threshold_does_not_create_a_targeted_trigger(cards, quests):
    s, source, bear = setup(cards, quests)
    assert s.state.cards[source.id].counters['quest'] == quests + 1
    assert s.state.rules.decision is None and not s.state.rules.stack
    assert not s.state.cards[bear.id].counters and not has_trample(s, cards, bear)


@pytest.mark.parametrize('quests', [3, 4])
def test_actual_landfall_creates_separate_targeted_ability_after_counter_is_put(cards, quests):
    s, source, bear = setup(cards, quests)
    assert s.state.cards[source.id].counters['quest'] == quests + 1
    choose_bear(s, bear)
    assert s.state.rules.stack
    settle(s)
    assert s.state.cards[bear.id].counters['+1/+1'] == 1 and has_trample(s, cards, bear)
    roundtrip(s)


def test_prevented_counter_does_not_create_reflexive_trigger(cards):
    s, source, bear = setup(cards, 3, 'Solemnity')
    assert s.state.cards[source.id].counters['quest'] == 3
    assert s.state.rules.decision is None and not s.state.rules.stack
    assert not s.state.cards[bear.id].counters


def test_real_hexmage_removing_counters_stops_both_counter_and_trample(cards):
    s, source, bear = setup(cards)
    choose_bear(s, bear)
    hexmage = put(s, 'Vampire Hexmage', 'battlefield', pid='p2')
    wait_priority(s, 'p2')
    ch = Plan(s.state, 'p2', cards, None).ch(s.state.cards[hexmage.id])
    ability = next(a.index for a in ch.abilities if a.kind == 'activated')
    act(s, 'p2', type='activate_ability', card_id=hexmage.id, ability=ability, targets=[source.id])
    settle(s)
    assert not s.state.cards[source.id].counters
    assert not s.state.cards[bear.id].counters and not has_trample(s, cards, bear)
    roundtrip(s)


@pytest.mark.parametrize('returns', [False, True])
def test_source_departure_uses_original_objects_last_known_counters(cards, returns):
    s, source, bear = setup(cards)
    choose_bear(s, bear)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    if returns:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
        assert not s.state.cards[source.id].counters
    settle(s)
    assert s.state.cards[bear.id].counters['+1/+1'] == 1 and has_trample(s, cards, bear)
    roundtrip(s)


def test_doubled_quest_counter_addition_triggers_for_each_actual_counter(cards):
    s, source, bear = setup(cards, 2, 'Doubling Season')
    assert s.state.cards[source.id].counters['quest'] == 4
    for _ in range(2):
        choose_bear(s, bear)
        settle(s)
    assert s.state.rules.decision is None and not s.state.rules.stack
    assert s.state.cards[bear.id].counters['+1/+1'] == 4
    roundtrip(s)


def test_real_etb_earthbends_existing_land_then_searches_another_land(cards):
    s = table(cards, [NAME, 'Forest', 'Grizzly Bears'], [])
    source = put(s, NAME, 'hand')
    land = put(s, 'Forest', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'G': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[land.id], sources=[])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and any(o.id == land.id for o in d.options)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[land.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    eligible = [o for o in d.options if o.card_id and s.state.cards[o.card_id].zone == 'p1:library']
    assert eligible
    chosen = eligible[0]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[chosen.id])
    settle(s)
    assert s.state.cards[land.id].counters['+1/+1'] == 2
    assert s.state.cards[chosen.card_id].zone == 'p1:battlefield' and s.state.cards[chosen.card_id].tapped
    assert s.state.cards[source.id].counters['quest'] == 1
    roundtrip(s)
