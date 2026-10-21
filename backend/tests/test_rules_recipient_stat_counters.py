"""Counters use the current characteristic of each separate recipient."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/recipient_stat_counter_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()





def setup(cards):
    s = table(cards, ['Canopy Gargantuan', 'Grizzly Bears', 'Wall of Frost', 'Llanowar Elves', 'Hardened Scales', 'Doubling Season', 'Giant Growth', 'All Will Be One'],
              ['Grizzly Bears', 'Stifle', 'Lightning Bolt'], ['Grizzly Bears'])
    source = put(s, 'Canopy Gargantuan', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    wall = put(s, 'Wall of Frost', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    return s, source, bear, wall, elf


def upkeep(s):
    act(s, 'p1', type='next_turn', player='p1', force=True)
    for _ in range(10):
        act(s, s.state.rules.priority, type='pass_priority')
        if s.state.zones.get('stack'):
            return
    raise AssertionError('upkeep did not trigger')


def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Canopy Gargantuan')).level == 'FULL'


def test_each_recipient_uses_own_toughness_and_source_is_excluded(cards):
    s, source, bear, wall, elf = setup(cards)
    other = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    upkeep(s)
    settle(s)
    assert s.state.cards[bear.id].counters.get('+1/+1') == 2
    assert s.state.cards[wall.id].counters.get('+1/+1') == 7
    assert s.state.cards[elf.id].counters.get('+1/+1') == 1
    assert not s.state.cards[source.id].counters
    assert not s.state.cards[other.id].counters
    roundtrip(s)


def test_existing_counters_are_part_of_each_current_toughness(cards):
    s, _, bear, wall, _ = setup(cards)
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=3)
    act(s, 'p1', type='counter', card_ids=[wall.id], kind='-1/-1', delta=2)
    upkeep(s)
    roundtrip(s)
    settle(s)
    assert s.state.cards[bear.id].counters.get('+1/+1') == 8  # existing three + current toughness five
    assert s.state.cards[wall.id].counters.get('+1/+1') == 3  # five added; two opposing counters annihilate
    assert not s.state.cards[wall.id].counters.get('-1/-1')
    roundtrip(s)


def test_toughness_is_read_at_resolution_after_giant_growth(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s, _, bear, _, _ = setup(cards)
    upkeep(s)
    spell = put(s, 'Giant Growth', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1})
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id], sources=[])
    settle(s)
    assert s.state.cards[bear.id].counters.get('+1/+1') == 5
    roundtrip(s)


@pytest.mark.parametrize(('replacement', 'bear_count', 'wall_count'), [
    ('Hardened Scales', 3, 8), ('Doubling Season', 4, 14),
])
def test_each_amount_uses_normal_counter_replacements(cards, replacement, bear_count, wall_count):
    s, source, bear, wall, _ = setup(cards)
    put(s, replacement, 'battlefield')
    upkeep(s)
    settle(s)
    assert s.state.cards[bear.id].counters.get('+1/+1') == bear_count
    assert s.state.cards[wall.id].counters.get('+1/+1') == wall_count
    assert not s.state.cards[source.id].counters
    roundtrip(s)


@pytest.mark.parametrize('blink', [False, True])
def test_source_leaving_does_not_stop_trigger_and_new_object_is_other(cards, blink):
    s, source, bear, wall, _ = setup(cards)
    upkeep(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    if blink:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    roundtrip(s)
    settle(s)
    assert s.state.cards[bear.id].counters.get('+1/+1') == 2
    assert s.state.cards[wall.id].counters.get('+1/+1') == 7
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == (7 if blink else 0)
    roundtrip(s)


def test_recipient_set_uses_current_controller_and_current_objects(cards):
    s, _, bear, wall, _ = setup(cards)
    upkeep(s)
    act(s, 'p1', type='set_controller', card_ids=[bear.id], player='p2')
    act(s, 'p1', type='move', card_ids=[wall.id], to={'player': 'p1', 'zone': 'hand'})
    entrant = put(s, 'Grizzly Bears', 'battlefield', pid='p3')
    act(s, 'p3', type='set_controller', card_ids=[entrant.id], player='p1')
    settle(s)
    assert not s.state.cards[bear.id].counters
    assert not s.state.cards[wall.id].counters
    assert s.state.cards[entrant.id].counters.get('+1/+1') == 2
    roundtrip(s)


def test_stifle_counters_the_upkeep_trigger(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s, _, bear, _, _ = setup(cards)
    upkeep(s)
    ability = next(iter(s.state.rules.stack))
    spell = put(s, 'Stifle', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[ability], sources=[])
    settle(s)
    assert not s.state.cards[bear.id].counters
    roundtrip(s)


def test_recipients_counter_events_trigger_all_will_be_one_for_actual_amounts(cards):
    s, _, _, _, _ = setup(cards)
    put(s, 'All Will Be One', 'battlefield')
    upkeep(s)
    for _ in range(20):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        assert any(o.id == 'p2' for o in d.options)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 30  # two + seven + one; no counters on the 7/7 source
    roundtrip(s)


def test_changing_source_controller_does_not_change_trigger_controller(cards):
    s, source, bear, wall, _ = setup(cards)
    other = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    upkeep(s)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert s.state.cards[bear.id].counters.get('+1/+1') == 2
    assert s.state.cards[wall.id].counters.get('+1/+1') == 7
    assert not s.state.cards[other.id].counters
    assert not s.state.cards[source.id].counters
    roundtrip(s)
