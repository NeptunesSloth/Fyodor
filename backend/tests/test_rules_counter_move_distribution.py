"""CR 122.5: allocating moved counters among creatures."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/counter_move_distribution_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_forgotten_ancient_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Forgotten Ancient')).level == 'FULL'


def setup_upkeep(cards, *, scales=False, solemnity=False, count=4, accept=True, doubling=False):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Forgotten Ancient', 'Grizzly Bears', 'Hardened Scales', 'Solemnity', 'Doubling Season'], ['Grizzly Bears'], [])
    ancient = put(s, 'Forgotten Ancient', 'battlefield')
    own = put(s, 'Grizzly Bears', 'battlefield')
    opponent = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[ancient.id], kind='+1/+1', delta=count)
    if scales:
        put(s, 'Hardened Scales', 'battlefield')
    if doubling:
        put(s, 'Doubling Season', 'battlefield')
    if solemnity:
        put(s, 'Solemnity', 'battlefield')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    if d and {o.id for o in d.options} == {'yes', 'no'}:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes' if accept else 'no'])
        settle(s)
    return s, ancient, own, opponent


def answer(s, option):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    d = s.state.rules.decision
    assert d, option
    assert option in {o.id for o in d.options}, (option, [(o.id, o.label) for o in d.options])
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])


def test_distribute_to_own_and_opponents_creatures_leaving_some_counters(cards):
    from tests.test_rules_designations import roundtrip, settle

    s, ancient, own, other = setup_upkeep(cards)
    d = s.state.rules.decision
    assert d and ancient.id not in {o.id for o in d.options}
    answer(s, own.id)
    answer(s, '1')
    answer(s, other.id)
    answer(s, '2')
    # Choices are an allocation: no counters move until the player finishes.
    assert s.state.cards[ancient.id].counters['+1/+1'] == 4
    assert not s.state.cards[own.id].counters.get('+1/+1')
    answer(s, 'done')
    settle(s)
    assert s.state.cards[ancient.id].counters['+1/+1'] == 1
    assert s.state.cards[own.id].counters['+1/+1'] == 1
    assert s.state.cards[other.id].counters['+1/+1'] == 2
    roundtrip(s)


@pytest.mark.parametrize('scales', [False, True])
def test_moving_all_counters_applies_recipient_replacements(cards, scales):
    from tests.test_rules_designations import roundtrip, settle

    s, ancient, own, other = setup_upkeep(cards, scales=scales)
    answer(s, own.id)
    answer(s, '4')
    settle(s)
    assert s.state.cards[ancient.id].counters.get('+1/+1', 0) == 0
    assert s.state.cards[own.id].counters['+1/+1'] == 4 + int(scales)
    assert s.state.cards[other.id].counters.get('+1/+1', 0) == 0
    roundtrip(s)


@pytest.mark.parametrize('solemnity,count', [(False, 4), (True, 4), (False, 0)])
def test_zero_moves_or_counter_prohibition_preserves_source_counters(cards, solemnity, count):
    from tests.test_rules_designations import roundtrip, settle

    s, ancient, own, other = setup_upkeep(cards, solemnity=solemnity, count=count)
    if not solemnity and count:
        answer(s, 'done')
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[ancient.id].counters.get('+1/+1', 0) == count
    assert not s.state.cards[own.id].counters.get('+1/+1')
    assert not s.state.cards[other.id].counters.get('+1/+1')
    roundtrip(s)


def test_repeated_recipient_accumulates_allocation_and_invalid_amount_is_rejected(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, ancient, own, other = setup_upkeep(cards)
    answer(s, own.id)
    d = s.state.rules.decision
    assert d
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['5'])
    answer(s, '1')
    answer(s, own.id)
    answer(s, '2')
    answer(s, 'done')
    settle(s)
    assert s.state.cards[ancient.id].counters['+1/+1'] == 1
    assert s.state.cards[own.id].counters['+1/+1'] == 3
    assert not s.state.cards[other.id].counters.get('+1/+1')
    roundtrip(s)


def test_declining_upkeep_trigger_preserves_counters(cards):
    from tests.test_rules_designations import roundtrip

    s, ancient, own, other = setup_upkeep(cards, accept=False)
    assert s.state.rules.decision is None
    assert s.state.cards[ancient.id].counters['+1/+1'] == 4
    assert not s.state.cards[own.id].counters.get('+1/+1')
    assert not s.state.cards[other.id].counters.get('+1/+1')
    roundtrip(s)


def test_counter_replacement_order_pauses_without_removing_source_twice(cards):
    from tests.test_rules_designations import roundtrip, settle

    s, ancient, own, _ = setup_upkeep(cards, scales=True, doubling=True)
    answer(s, own.id)
    answer(s, '4')
    assert s.state.cards[ancient.id].counters.get('+1/+1', 0) == 0
    d = s.state.rules.decision
    assert d and '616.1' in d.prompt
    roundtrip(s)
    answer(s, d.options[0].id)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[ancient.id].counters.get('+1/+1', 0) == 0
    assert s.state.cards[own.id].counters['+1/+1'] in (9, 10)
    roundtrip(s)


def test_source_leaving_before_trigger_resolves_prevents_counter_moves(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Forgotten Ancient', 'Grizzly Bears'], [], [])
    source = put(s, 'Forgotten Ancient', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=4)
    to_phase(s, 'upkeep', turn=4)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    d = s.state.rules.decision
    if d:
        assert {o.id for o in d.options} == {'yes', 'no'}
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes'])
        settle(s)
    assert s.state.rules.decision is None
    assert not s.state.cards[bear.id].counters.get('+1/+1')
    roundtrip(s)
