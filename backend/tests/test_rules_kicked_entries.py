"""Canonical compound entry replacements, including discarded-card provenance."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/kicked_entry_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='kie', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Ravaging Riftwurm', 'Voidpouncer', 'Prison Barricade', "Dralnu's Pet"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name,mana,counters,keywords', [
    ('Ravaging Riftwurm', {'G': 2, 'C': 5}, {'time': 5}, []),
    ('Voidpouncer', {'R': 1, 'C': 4}, {'+1/+1': 2, 'trample': 1}, ['haste', 'trample']),
    ('Prison Barricade', {'W': 2, 'C': 2}, {'+1/+1': 1}, []),
])
@pytest.mark.parametrize('kicked', [False, True])
def test_paid_kicker_controls_every_entry_counter_and_grant(cards, name, mana, counters, keywords, kicked):
    s = table(cards, [name])
    entrant = put(s, name, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=entrant.id, kicker=int(kicked))
    settle(s)
    obj = s.state.cards[entrant.id]
    assert obj.counters == (counters if kicked else {'time': 2} if name == 'Ravaging Riftwurm' else {})
    plan = Plan(s.state, 'p1', cards, None)
    ch = plan.ch(obj)
    for keyword in keywords:
        assert (keyword in ch.keywords) == kicked
    if name == 'Prison Barricade':
        assert ('attack_despite_defender' in scripts.statics(ch)) == kicked
    roundtrip(s)


@pytest.mark.parametrize('discard_name,expected', [('Grizzly Bears', 2), ('Ornithopter', 0)])
@pytest.mark.parametrize('solemnity', [False, True])
def test_discarded_mana_value_zero_still_grants_flying(cards, discard_name, expected, solemnity):
    s = table(cards, ["Dralnu's Pet", discard_name, 'Solemnity'])
    if solemnity:
        put(s, 'Solemnity', 'battlefield')
    discard = put(s, discard_name, 'hand')
    entrant = put(s, "Dralnu's Pet", 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'B': 1, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=entrant.id, kicker=1,
        cost_choices=[{'component': 0, 'cards': [discard.id]}])
    settle(s)
    obj = s.state.cards[entrant.id]
    assert obj.counters.get('+1/+1', 0) == (0 if solemnity else expected)
    assert 'flying' in Plan(s.state, 'p1', cards, None).ch(obj).keywords
    assert s.state.cards[discard.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_discarded_object_lki_survives_reanimation_as_a_different_copy(cards):
    s = table(cards, ["Dralnu's Pet", 'Phantasmal Image', 'Air Elemental'], ['Reanimate', 'Vedalken Orrery'])
    put(s, 'Vedalken Orrery', 'battlefield', 'p2')
    donor = put(s, 'Air Elemental', 'battlefield')
    discard = put(s, 'Phantasmal Image', 'hand')
    entrant = put(s, "Dralnu's Pet", 'hand')
    reanimate = put(s, 'Reanimate', 'hand', 'p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'B': 1, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=entrant.id, kicker=1,
        cost_choices=[{'component': 0, 'cards': [discard.id]}])
    act(s, 'p2', type='add_mana', player='p2', mana={'B': 1})
    act(s, 'p2', type='cast_spell', card_id=reanimate.id, targets=[discard.id])
    settle(s)
    from app.game.session import GameSession
    from app.game.state import GameState

    s = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    pick(s, [donor.id])
    settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[discard.id]).mana_value == 5
    assert s.state.cards[entrant.id].counters == {'+1/+1': 2}
    roundtrip(s)


@pytest.mark.parametrize('name,mana,expected', [
    ('Ravaging Riftwurm', {'G': 2, 'C': 5}, {'time': 10}),
    ('Voidpouncer', {'R': 1, 'C': 4}, {'+1/+1': 4, 'trample': 2}),
    ('Prison Barricade', {'W': 2, 'C': 2}, {'+1/+1': 2}),
])
def test_native_doubling_applies_to_all_kicked_entry_counters(cards, name, mana, expected):
    s = table(cards, [name, 'Doubling Season'])
    put(s, 'Doubling Season', 'battlefield')
    entrant = put(s, name, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=entrant.id, kicker=1)
    settle(s)
    assert s.state.cards[entrant.id].counters == expected
    roundtrip(s)


def test_later_ability_removal_removes_granted_defender_permission(cards):
    s = table(cards, ['Prison Barricade', 'Humility'])
    entrant = put(s, 'Prison Barricade', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 2, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=entrant.id, kicker=1)
    settle(s)
    assert 'attack_despite_defender' in scripts.statics(Plan(s.state, 'p1', cards, None).ch(s.state.cards[entrant.id]))
    humility = put(s, 'Humility', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 2, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=humility.id)
    settle(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[entrant.id])
    assert not ch.abilities
    assert 'attack_despite_defender' not in scripts.statics(ch)
    roundtrip(s)


def test_native_creature_spell_copy_inherits_kicker_and_discarded_cost_object(cards):
    s = table(cards, ["Dralnu's Pet", 'Grizzly Bears', 'Double Major'])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    discard = put(s, 'Grizzly Bears', 'hand')
    entrant = put(s, "Dralnu's Pet", 'hand')
    copier = put(s, 'Double Major', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 3, 'G': 1, 'B': 1, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=entrant.id, kicker=1,
        cost_choices=[{'component': 0, 'cards': [discard.id]}])
    act(s, 'p1', type='cast_spell', card_id=copier.id, targets=[entrant.id])
    settle(s)
    copies = [c for c in s.state.cards.values() if c.zone == 'p1:battlefield'
              and Plan(s.state, 'p1', cards, None).ch(c).name == "Dralnu's Pet"]
    assert len(copies) == 2
    for obj in copies:
        assert obj.counters == {'+1/+1': 2}
        assert 'flying' in Plan(s.state, 'p1', cards, None).ch(obj).keywords
    roundtrip(s)
