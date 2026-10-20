"""Ichormoon Gauntlet uses the native one-counter-kind resolution machinery."""
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

NAME = 'Ichormoon Gauntlet'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/ichormoon_counter_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='ich', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, extra=()):
    s = table(cards, [NAME, 'Sol Ring', 'Grizzly Bears', *extra], ['Grizzly Bears'])
    source = put(s, NAME, 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    return s, source, target


def cast_and_target(s, target):
    spell = put(s, 'Sol Ring', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert target.id in {o.id for o in s.state.rules.decision.options}
    pick(s, [target.id])


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_choose_one_kind_not_all_or_total(cards):
    s, source, target = setup(cards)
    act(s, 'p2', type='set_counter', card_id=target.id, kind='charge', value=4)
    act(s, 'p2', type='set_counter', card_id=target.id, kind='+1/+1', value=2)
    cast_and_target(s, target)
    settle(s)
    assert {o.id for o in s.state.rules.decision.options} == {'charge', '+1/+1'}
    roundtrip(s)
    pick(s, ['charge'])
    settle(s)
    assert s.state.cards[target.id].counters == {'charge': 5, '+1/+1': 2}
    roundtrip(s)


@pytest.mark.parametrize('kind', [None, 'shield', 'loyalty'])
def test_no_counters_or_only_one_kind(cards, kind):
    s, source, target = setup(cards)
    if kind is not None:
        act(s, 'p2', type='set_counter', card_id=target.id, kind=kind, value=3)
    cast_and_target(s, target)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[target.id].counters == ({} if kind is None else {kind: 4})
    roundtrip(s)


def test_creature_spell_does_not_trigger(cards):
    s, source, target = setup(cards)
    spell = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.cards[target.id].counters
    roundtrip(s)


def test_counter_replacement_and_source_departure(cards):
    s, source, target = setup(cards, ['Doubling Season'])
    own = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=own.id, kind='charge', value=2)
    cast_and_target(s, own)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[own.id].counters['charge'] == 4
    roundtrip(s)


def test_target_new_object_does_not_receive_counter(cards):
    s, source, target = setup(cards)
    act(s, 'p2', type='set_counter', card_id=target.id, kind='charge', value=2)
    cast_and_target(s, target)
    act(s, 'p2', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'exile'})
    act(s, 'p2', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'battlefield'})
    settle(s)
    assert not s.state.cards[target.id].counters
    roundtrip(s)
