"""Canoptek Spyder distinguishes artifact creatures from other artifacts and creatures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, selectors
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = 'Canoptek Spyder'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/canoptek_spyder_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, extra):
    s = table(cards, [NAME, *extra], ['Myr Retriever', "Smuggler's Copter"])
    source = put(s, NAME, 'hand')
    mana(s, G=1, C=5)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before - 1  # The Spyder does not trigger on itself.
    return s, source


def test_full_and_compound_union_keeps_qualifiers(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'
    sel = selectors.parse('another nontoken artifact creature or Vehicle you control')
    assert sel and len(sel.either) == 2
    artifact, vehicle = [selectors.from_key(k) for k in sel.either]
    assert set(artifact.types) == {'Artifact', 'Creature'} and 'all_types' in artifact.extras
    assert vehicle.subtypes == ('Vehicle',)
    assert all(s.other and s.token is False and s.controller == 'you' for s in (artifact, vehicle))
    assert selectors.parse('another nontoken artifact creature or Notarealsubtype you control') is None


@pytest.mark.parametrize(('name', 'payment', 'draw'), [
    ('Myr Retriever', {'C': 2}, True),
    ("Smuggler's Copter", {'C': 2}, True),
    ('Grizzly Bears', {'G': 1, 'C': 1}, False),
    ('Sol Ring', {'C': 1}, False),
])
def test_actual_casts_only_eligible_branches_draw(cards, name, payment, draw):
    s, _ = setup(cards, [name])
    spell = put(s, name, 'hand')
    mana(s, **payment)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert len(s.state.zones['p1:hand']) == before - 1 + int(draw)
    roundtrip(s)


def test_opponents_objects_and_tokens_in_either_branch_do_not_draw(cards):
    from tests.test_rules_conditionals import token_of

    s, _ = setup(cards, [])
    before = len(s.state.zones['p1:hand'])
    for name in ['Myr Retriever', "Smuggler's Copter"]:
        put(s, name, 'battlefield', pid='p2')
        settle(s)
    token_of(s, 'p1', 'Myr', 'Token Artifact Creature — Myr', '2/2')
    token_of(s, 'p1', 'Vehicle', 'Token Artifact — Vehicle', '2/2')
    settle(s)
    assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)


def test_animated_vehicle_matches_both_branches_but_draws_once(cards):
    s, _ = setup(cards, ['March of the Machines', "Smuggler's Copter"])
    march = put(s, 'March of the Machines', 'hand')
    mana(s, U=1, C=3)
    act(s, 'p1', type='cast_spell', card_id=march.id, targets=[])
    settle(s)
    copter = put(s, "Smuggler's Copter", 'hand')
    mana(s, C=2)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=copter.id, targets=[])
    settle(s)
    from app.rules.plan import Plan
    ch = Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[copter.id])
    assert ch.is_creature and 'Artifact' in ch.types and 'Vehicle' in ch.subtypes
    assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)
