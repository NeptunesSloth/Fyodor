"""Entry values bind payment objects, draw history, and a chosen opponent."""
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
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/entry_value_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='evc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Murktide Regent', 'Sheriff of Safe Passage', 'Thought Sponge', 'Slumbering Trudge', 'Canker Abomination'])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('others', [0, 1, 2])
def test_sheriff_base_plus_other_existing_creatures(cards, others):
    s = table(cards, ['Sheriff of Safe Passage', 'Grizzly Bears', 'Hill Giant'])
    for name in ['Grizzly Bears', 'Hill Giant'][:others]:
        put(s, name, 'battlefield')
    entrant = put(s, 'Sheriff of Safe Passage', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=entrant.id)
    settle(s)
    assert s.state.cards[entrant.id].counters == {'+1/+1': others + 1}
    roundtrip(s)


@pytest.mark.parametrize('x', [0, 1, 2, 3, 5])
def test_slumbering_counter_and_tapped_threshold(cards, x):
    s = table(cards, ['Slumbering Trudge'])
    entrant = put(s, 'Slumbering Trudge', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': x})
    act(s, 'p1', type='cast_spell', card_id=entrant.id, x_value=x)
    settle(s)
    obj = s.state.cards[entrant.id]
    assert obj.tapped == (x <= 2)
    assert obj.counters.get('stun', 0) == max(0, 3 - x)
    roundtrip(s)


@pytest.mark.parametrize('opponent,expected', [('p2', 1), ('p3', 2)])
def test_canker_preentry_opponent_choice(cards, opponent, expected):
    from app.game.session import GameSession
    from app.game.state import GameState

    s = table(cards, ['Canker Abomination'], ['Grizzly Bears'], ['Grizzly Bears', 'Hill Giant'])
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Grizzly Bears', 'battlefield', 'p3')
    put(s, 'Hill Giant', 'battlefield', 'p3')
    entrant = put(s, 'Canker Abomination', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'B': 1, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=entrant.id)
    settle(s)
    assert s.state.rules.decision is not None and s.state.cards[entrant.id].zone == 'stack'
    s = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    pick(s, [opponent])
    settle(s)
    assert s.state.cards[entrant.id].counters == {'-1/-1': expected}
    roundtrip(s)


@pytest.mark.parametrize('departed', [False, True])
def test_sponge_uses_maximum_per_opponent_draws_including_departed(cards, departed):
    s = table(cards, ['Thought Sponge', "Blue Sun's Zenith", 'Sign in Blood'])
    blue = put(s, "Blue Sun's Zenith", 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 3, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=blue.id, targets=['p2'], x_value=3)
    settle(s)
    sign = put(s, 'Sign in Blood', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2})
    act(s, 'p1', type='cast_spell', card_id=sign.id, targets=['p3'])
    settle(s)
    if departed:
        act(s, 'p2', type='concede')
    entrant = put(s, 'Thought Sponge', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=entrant.id)
    settle(s)
    assert s.state.cards[entrant.id].counters == {'+1/+1': 3}
    roundtrip(s)


def test_murktide_counts_only_instant_sorcery_delve_cost_objects(cards):
    s = table(cards, ['Murktide Regent', 'Lightning Bolt', 'Divination', 'Grizzly Bears'])
    used = [put(s, name, 'graveyard') for name in ['Lightning Bolt', 'Divination', 'Grizzly Bears']]
    entrant = put(s, 'Murktide Regent', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=entrant.id,
        contributions=[{'kind': 'delve', 'card': c.id} for c in used])
    settle(s)
    assert s.state.cards[entrant.id].counters == {'+1/+1': 2}
    assert all(s.state.cards[c.id].zone.endswith(':exile') for c in used)
    roundtrip(s)


def test_sheriff_does_not_count_simultaneous_living_death_arrivals(cards):
    s = table(cards, ['Sheriff of Safe Passage', 'Grizzly Bears', 'Living Death'], ['Hill Giant'])
    sheriff = put(s, 'Sheriff of Safe Passage', 'graveyard')
    put(s, 'Grizzly Bears', 'graveyard')
    put(s, 'Hill Giant', 'graveyard', 'p2')
    spell = put(s, 'Living Death', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[sheriff.id].counters == {'+1/+1': 1}
    roundtrip(s)


@pytest.mark.parametrize('name,expected,tapped', [('Murktide Regent', 0, False), ('Slumbering Trudge', 3, True)])
def test_uncast_entry_has_no_payment_and_zero_x(cards, name, expected, tapped):
    s = table(cards, [name, 'Reanimate'])
    entrant = put(s, name, 'graveyard')
    spell = put(s, 'Reanimate', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[entrant.id])
    settle(s)
    obj = s.state.cards[entrant.id]
    assert obj.tapped == tapped
    assert sum(obj.counters.values()) == expected
    roundtrip(s)


def test_murktide_cost_objects_count_even_if_they_leave_exile_while_spell_pending(cards):
    s = table(cards, ['Murktide Regent', 'Lightning Bolt', 'Divination'], ['Pull from Eternity'])
    used = [put(s, name, 'graveyard') for name in ['Lightning Bolt', 'Divination']]
    entrant = put(s, 'Murktide Regent', 'hand')
    pull = put(s, 'Pull from Eternity', 'hand', 'p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=entrant.id,
        contributions=[{'kind': 'delve', 'card': c.id} for c in used])
    act(s, 'p2', type='add_mana', player='p2', mana={'W': 1})
    act(s, 'p2', type='cast_spell', card_id=pull.id, targets=[used[0].id])
    settle(s)
    assert s.state.cards[used[0].id].zone == 'p1:graveyard'
    assert s.state.cards[entrant.id].counters == {'+1/+1': 2}
    roundtrip(s)


def test_murktide_spell_copy_retains_original_delve_objects(cards):
    s = table(cards, ['Murktide Regent', 'Lightning Bolt', 'Divination', 'Double Major'])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    used = [put(s, name, 'graveyard') for name in ['Lightning Bolt', 'Divination']]
    entrant = put(s, 'Murktide Regent', 'hand')
    copier = put(s, 'Double Major', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 3, 'G': 1, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=entrant.id,
        contributions=[{'kind': 'delve', 'card': c.id} for c in used])
    act(s, 'p1', type='cast_spell', card_id=copier.id, targets=[entrant.id])
    settle(s)
    entered = [c for c in s.state.cards.values() if c.zone == 'p1:battlefield' and c.name == 'Murktide Regent']
    assert len(entered) == 2
    assert all(c.counters == {'+1/+1': 2} for c in entered)
    roundtrip(s)
