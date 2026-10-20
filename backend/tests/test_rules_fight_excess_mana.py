"""Fight recipient excess and turn-long red mana retention."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/fight_excess_mana_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




def setup(cards, mine='Colossal Dreadmaw', theirs='Grizzly Bears'):
    s = table(cards, ['The Last Agni Kai', mine, 'Ambush Viper', 'Mountain', 'Leyline Tyrant'], [theirs, 'Furnace of Rath'], ['Healing Salve'])
    a = put(s, mine, 'battlefield')
    b = put(s, theirs, 'battlefield', pid='p2')
    spell = put(s, 'The Last Agni Kai', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    return s, a, b, spell


def cast(s, spell, a, b):
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[a.id, b.id], target_counts=[1, 1], sources=[])
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve('The Last Agni Kai')).level == 'FULL'


@pytest.mark.parametrize(('mine', 'theirs', 'red'), [
    ('Colossal Dreadmaw', 'Grizzly Bears', 4),
    ('Grizzly Bears', 'Colossal Dreadmaw', 0),
    ('Ambush Viper', 'Colossal Dreadmaw', 1),
    ('Colossal Dreadmaw', 'Darksteel Myr', 5),
])
def test_only_opponents_excess_counts_with_simultaneous_fight(cards, mine, theirs, red):
    from tests.game_helpers import mana_pool
    s, a, b, spell = setup(cards, mine, theirs)
    cast(s, spell, a, b)
    assert mana_pool(s).get('R', 0) == red
    roundtrip(s)


def test_preexisting_damage_reduces_lethal_threshold(cards):
    from tests.game_helpers import mana_pool
    s, a, b, spell = setup(cards)
    act(s, 'p2', type='set_damage', card_ids=[b.id], value=1)
    cast(s, spell, a, b)
    assert mana_pool(s).get('R', 0) == 5
    roundtrip(s)


def test_replacement_increases_actual_excess(cards):
    from tests.game_helpers import mana_pool
    s, a, b, spell = setup(cards)
    put(s, 'Furnace of Rath', 'battlefield', pid='p2')
    cast(s, spell, a, b)
    assert mana_pool(s).get('R', 0) == 10
    roundtrip(s)


@pytest.mark.parametrize('gone', ['mine', 'theirs'])
def test_one_illegal_target_prevents_fight_but_retention_still_applies(cards, gone):
    from tests.game_helpers import mana_pool
    s, a, b, spell = setup(cards)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[a.id, b.id], target_counts=[1, 1], sources=[])
    victim = a if gone == 'mine' else b
    act(s, victim.owner, type='move', card_ids=[victim.id], to={'player': victim.owner, 'zone': 'hand'})
    settle(s)
    assert mana_pool(s).get('R', 0) == 0
    assert s.state.rules.kept_mana
    roundtrip(s)


def advance(s):
    phase = s.state.turn.phase
    for _ in range(20):
        act(s, s.state.rules.priority, type='pass_priority')
        if s.state.turn.phase != phase:
            return
    raise AssertionError('step did not advance')


def test_turn_retention_keeps_existing_and_future_red_but_not_other_mana(cards):
    from tests.game_helpers import mana_pool
    s, a, b, spell = setup(cards, 'Grizzly Bears', 'Colossal Dreadmaw')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 3, 'G': 2})
    cast(s, spell, a, b)
    assert mana_pool(s).get('R') == 3
    advance(s)
    assert mana_pool(s) == {'R': 3}
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 7, 'G': 2})
    advance(s)
    assert mana_pool(s) == {'R': 10}
    roundtrip(s)
    turn = s.state.turn.number
    for _ in range(30):
        if s.state.turn.number != turn:
            break
        advance(s)
    assert mana_pool(s).get('R', 0) == 0, (s.state.turn, s.state.rules.kept_mana)
    roundtrip(s)


def test_retention_survives_an_initially_empty_red_pool(cards):
    from tests.game_helpers import mana_pool
    s, a, b, spell = setup(cards, 'Grizzly Bears', 'Colossal Dreadmaw')
    cast(s, spell, a, b)
    advance(s)
    assert not mana_pool(s)
    assert s.state.rules.kept_mana
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 7})
    advance(s)
    assert mana_pool(s) == {'R': 7}
    roundtrip(s)


def test_future_source_identified_red_units_are_retained(cards):
    from tests.game_helpers import mana_pool
    s, a, b, spell = setup(cards, 'Grizzly Bears', 'Colossal Dreadmaw')
    cast(s, spell, a, b)
    land = put(s, 'Mountain', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=0)
    assert any(u.sym == 'R' and u.src for u in s.state.players['p1'].mana_units)
    advance(s)
    assert mana_pool(s) == {'R': 1}
    assert any(u.sym == 'R' and u.src for u in s.state.players['p1'].mana_units)
    roundtrip(s)


def test_protection_prevents_fighting_damage_and_excess(cards):
    from tests.game_helpers import mana_pool
    s, a, b, spell = setup(cards, 'Colossal Dreadmaw', 'Mirran Crusader')
    cast(s, spell, a, b)
    assert mana_pool(s).get('R', 0) == 0
    assert s.state.cards[b.id].zone == 'p2:battlefield'
    assert s.state.cards[b.id].damage == 0
    assert s.state.cards[a.id].damage == 2  # double strike does not change fight damage
    roundtrip(s)


def test_prevention_reduces_actual_fight_excess(cards):
    from tests.game_helpers import mana_pool
    from tests.test_rules_bandmate_references import wait_priority
    s, a, b, spell = setup(cards)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[a.id, b.id], target_counts=[1, 1], sources=[])
    shield = put(s, 'Healing Salve', 'hand', pid='p3')
    act(s, 'p3', type='add_mana', player='p3', mana={'W': 1})
    wait_priority(s, 'p3')
    act(s, 'p3', type='cast_spell', card_id=shield.id, modes=[1], targets=[b.id], sources=[])
    settle(s)
    assert mana_pool(s).get('R', 0) == 1  # six dealt, three prevented, two lethal
    roundtrip(s)


def test_permanent_red_retention_still_keeps_mana_after_cleanup(cards):
    from tests.game_helpers import mana_pool
    s, a, b, spell = setup(cards, 'Grizzly Bears', 'Colossal Dreadmaw')
    put(s, 'Leyline Tyrant', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 3})
    cast(s, spell, a, b)
    turn = s.state.turn.number
    for _ in range(30):
        if s.state.turn.number != turn:
            break
        advance(s)
    assert s.state.turn.number != turn
    assert mana_pool(s) == {'R': 3}
    assert not any(rec.get('color') for rec in s.state.rules.kept_mana)
    roundtrip(s)


def test_all_targets_illegal_counter_spell_without_retention(cards):
    s, a, b, spell = setup(cards)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[a.id, b.id], target_counts=[1, 1], sources=[])
    for victim in (a, b):
        act(s, victim.owner, type='move', card_ids=[victim.id], to={'player': victim.owner, 'zone': 'hand'})
    settle(s)
    assert not s.state.rules.kept_mana
    roundtrip(s)
