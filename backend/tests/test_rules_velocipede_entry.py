"""Conditional entry-counter amounts use the entering object's battlefield face."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/velocipede_entry_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='vce', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Thunderous Velocipede')).level == 'FULL'


def test_source_does_not_apply_to_its_own_entry(cards):
    s = table(cards, ['Thunderous Velocipede'])
    entrant = put(s, 'Thunderous Velocipede', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 2, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=entrant.id)
    settle(s)
    assert s.state.cards[entrant.id].zone == 'p1:battlefield'
    assert not s.state.cards[entrant.id].counters
    roundtrip(s)


@pytest.mark.parametrize('name,mana,expected', [
    ('Grizzly Bears', {'G': 1, 'C': 1}, 1),
    ('Hill Giant', {'R': 1, 'C': 3}, 1),
    ('Air Elemental', {'U': 2, 'C': 3}, 3),
    ('Ornithopter', {}, 1),
    ("Smuggler's Copter", {'C': 2}, 1),
])
def test_creatures_and_uncrewed_vehicles_use_incoming_mana_value(cards, name, mana, expected):
    s = table(cards, ['Thunderous Velocipede', name])
    put(s, 'Thunderous Velocipede', 'battlefield')
    entrant = put(s, name, 'hand')
    if mana:
        act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=entrant.id)
    settle(s)
    assert s.state.cards[entrant.id].counters == {'+1/+1': expected}
    roundtrip(s)


def test_opponents_do_not_receive_counters(cards):
    s = table(cards, ['Grizzly Bears'], ['Thunderous Velocipede'])
    put(s, 'Thunderous Velocipede', 'battlefield', 'p2')
    target = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=target.id)
    settle(s)
    assert not s.state.cards[target.id].counters
    roundtrip(s)


def test_x_is_zero_on_the_entering_permanent(cards):
    s = table(cards, ['Thunderous Velocipede', 'Stonecoil Serpent'])
    put(s, 'Thunderous Velocipede', 'battlefield')
    entrant = put(s, 'Stonecoil Serpent', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 5})
    act(s, 'p1', type='cast_spell', card_id=entrant.id, x_value=5)
    settle(s)
    assert s.state.cards[entrant.id].counters == {'+1/+1': 6}
    roundtrip(s)


@pytest.mark.parametrize('replacement,expected', [('Doubling Season', 6), ('Solemnity', 0)])
def test_additional_counters_use_normal_replacements(cards, replacement, expected):
    s = table(cards, ['Thunderous Velocipede', 'Air Elemental', replacement])
    put(s, 'Thunderous Velocipede', 'battlefield')
    put(s, replacement, 'battlefield')
    entrant = put(s, 'Air Elemental', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=entrant.id)
    settle(s)
    while s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert d.resume['step'] == 'replacement'
        pick(s, [d.options[0].id])
        settle(s)
    assert s.state.cards[entrant.id].counters.get('+1/+1', 0) == expected
    roundtrip(s)


def test_copy_replacement_uses_copied_mana_value_after_save(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s = table(cards, ['Thunderous Velocipede', 'Phantasmal Image', 'Air Elemental'])
    put(s, 'Thunderous Velocipede', 'battlefield')
    donor = put(s, 'Air Elemental', 'battlefield')
    entrant = put(s, 'Phantasmal Image', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=entrant.id)
    settle(s)
    assert s.state.rules.decision is not None
    s = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    pick(s, [donor.id])
    settle(s)
    assert s.state.cards[entrant.id].counters == {'+1/+1': 3}
    roundtrip(s)


@pytest.mark.parametrize('prior', [False, True])
def test_storm_entity_excludes_its_own_cast(cards, prior):
    s = table(cards, ['Storm Entity', 'Grizzly Bears'])
    if prior:
        bear = put(s, 'Grizzly Bears', 'hand')
        act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
        act(s, 'p1', type='cast_spell', card_id=bear.id)
        settle(s)
    entrant = put(s, 'Storm Entity', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=entrant.id)
    settle(s)
    assert coverage.of_card_data(cards.resolve('Storm Entity')).level == 'FULL'
    obj = s.state.cards[entrant.id]
    if prior:
        assert obj.zone == 'p1:battlefield' and obj.counters == {'+1/+1': 1}
    else:
        assert obj.zone == 'p1:battlefield' and not obj.counters
    roundtrip(s)


def test_reanimated_storm_entity_counts_reanimation_spell(cards):
    s = table(cards, ['Storm Entity', 'Reanimate'])
    entrant = put(s, 'Storm Entity', 'graveyard')
    spell = put(s, 'Reanimate', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[entrant.id])
    settle(s)
    assert s.state.cards[entrant.id].zone == 'p1:battlefield'
    assert s.state.cards[entrant.id].counters == {'+1/+1': 1}
    roundtrip(s)


def test_storm_entity_counts_opponents_casts(cards):
    s = table(cards, ['Storm Entity'], ['Lightning Bolt'])
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    act(s, 'p1', type='pass_priority')
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p1'])
    settle(s)
    entrant = put(s, 'Storm Entity', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=entrant.id)
    settle(s)
    assert s.state.cards[entrant.id].counters == {'+1/+1': 1}
    roundtrip(s)
