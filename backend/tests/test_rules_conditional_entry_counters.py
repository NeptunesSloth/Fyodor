"""Conditional entry counters use entering characteristics and native replacements."""
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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave5c_combat import to_attack
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/conditional_entry_counter_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='cec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, target='Grizzly Bears', extra=()):
    s = table(cards, ['Recommission', target, *extra])
    obj = put(s, target, 'graveyard')
    for name in extra:
        put(s, name, 'battlefield')
    return s, obj


def cast(s, target):
    spell = put(s, 'Recommission', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)


def test_recommission_full(cards):
    assert coverage.of_card_data(cards.resolve('Recommission')).level == 'FULL'


def test_heroic_return_full(cards):
    assert coverage.of_card_data(cards.resolve('Heroic Return')).level == 'FULL'


@pytest.mark.parametrize('target,extra,expected', [
    ('Grizzly Bears', (), 1),
    ('Sol Ring', (), 0),
    ('Sol Ring', ('March of the Machines',), 1),
    ('Ornithopter', ('March of the Machines',), 1),
    ('Grizzly Bears', ('Doubling Season',), 2),
    ('Grizzly Bears', ('Hardened Scales',), 2),
    ('Grizzly Bears', ('Solemnity',), 0),
])
def test_enters_with_counters_using_entering_type(cards, target, extra, expected):
    s, obj = setup(cards, target, extra)
    cast(s, obj)
    live = s.state.cards[obj.id]
    assert live.zone == 'p1:battlefield'
    assert live.counters.get('+1/+1', 0) == expected
    roundtrip(s)


def test_stale_target_not_returned(cards):
    s, obj = setup(cards)
    spell = put(s, 'Recommission', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[obj.id])
    act(s, 'p1', type='move', card_ids=[obj.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[obj.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[obj.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_entry_copy_choice_keeps_conditional_counters(cards):
    s, image = setup(cards, 'Phantasmal Image', ['Grizzly Bears'])
    bear = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.zone == 'p1:battlefield')
    cast(s, image)
    assert s.state.rules.decision is not None
    assert bear.id in {o.id for o in s.state.rules.decision.options}
    roundtrip(s)
    pick(s, [bear.id])
    settle(s)
    assert s.state.cards[image.id].zone == 'p1:battlefield'
    assert s.state.cards[image.id].counters['+1/+1'] == 1
    roundtrip(s)


@pytest.mark.parametrize('hero', [False, True])
def test_heroic_return_counter_count(cards, hero):
    name = 'Spectacular Spider-Man' if hero else 'Grizzly Bears'
    s = table(cards, ['Heroic Return', name])
    target = put(s, name, 'graveyard')
    spell = put(s, 'Heroic Return', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 5})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].counters.get('+1/+1', 0) == (2 if hero else 0)
    roundtrip(s)


@pytest.mark.parametrize('defender', ['p1', 'p3'])
def test_heroic_return_discount_only_when_attacking_caster(cards, defender):
    from app.game.errors import ActionError

    s = table(cards, ['Heroic Return', 'Spectacular Spider-Man'], ['Grizzly Bears'])
    target = put(s, 'Spectacular Spider-Man', 'graveyard')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_attack(s, 5)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': defender}])
    wait_priority(s, 'p1')
    spell = put(s, 'Heroic Return', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 3})
    if defender == 'p3':
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
        assert s.state.cards[target.id].zone == 'p1:graveyard'
    else:
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
        settle(s)
        assert s.state.cards[target.id].counters['+1/+1'] == 2
    roundtrip(s)


def test_time_twist_full(cards):
    assert coverage.of_card_data(cards.resolve("Teferi's Time Twist")).level == 'FULL'


@pytest.mark.parametrize('target,animate,expected', [
    ('Grizzly Bears', False, 1), ('Sol Ring', False, 0), ('Sol Ring', True, 1),
])
def test_time_twist_checks_type_on_delayed_entry(cards, target, animate, expected):
    s = table(cards, ["Teferi's Time Twist", target, 'March of the Machines'])
    obj = put(s, target, 'battlefield')
    spell = put(s, "Teferi's Time Twist", 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[obj.id])
    settle(s)
    assert s.state.cards[obj.id].zone == 'p1:exile'
    roundtrip(s)
    if animate:
        put(s, 'March of the Machines', 'battlefield')
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[obj.id].zone == 'p1:battlefield'
    assert s.state.cards[obj.id].counters.get('+1/+1', 0) == expected
    roundtrip(s)


def test_semester_end_full(cards):
    assert coverage.of_card_data(cards.resolve("Semester's End")).level == 'FULL'


def test_semester_end_adds_both_kinds_for_creature_planeswalker(cards):
    s = table(cards, ["Semester's End", 'Gideon Blackblade', 'Jace Beleren', 'Grizzly Bears'])
    gideon = put(s, 'Gideon Blackblade', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=gideon.id, kind='loyalty', value=4)
    jace = put(s, 'Jace Beleren', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=jace.id, kind='loyalty', value=3)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell = put(s, "Semester's End", 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[gideon.id, jace.id, bear.id], target_counts=[3])
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:exile' for c in [gideon, jace, bear])
    roundtrip(s)
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[gideon.id].counters == {'loyalty': 5, '+1/+1': 1}
    assert s.state.cards[jace.id].counters == {'loyalty': 4}
    assert s.state.cards[bear.id].counters == {'+1/+1': 1}
    roundtrip(s)


def test_simultaneous_return_does_not_use_other_arriving_static_for_entry_type(cards):
    s = table(cards, ["Semester's End", 'Opalescence', 'March of the Machines', 'Sol Ring'])
    put(s, 'Opalescence', 'battlefield')
    march = put(s, 'March of the Machines', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    spell = put(s, "Semester's End", 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[march.id, ring.id], target_counts=[2])
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:exile' for c in [march, ring])
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[march.id].counters == {'+1/+1': 1}
    assert not s.state.cards[ring.id].counters
    roundtrip(s)
