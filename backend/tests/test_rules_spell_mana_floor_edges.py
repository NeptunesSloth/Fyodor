"""CR 601.2f, 613.1f, 702.26: active spell-cost floors follow source state."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_spell_mana_floor import DATA

EXTRA = json.loads((Path(__file__).parent / 'fixtures/spell_mana_floor_edge_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate([*DATA, *EXTRA]):
        base[c['name']] = card(c['name'], set_code='tme', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, [c['name'] for c in [*DATA, *EXTRA]] + ['Trinisphere'], [], [])
    sphere_ids = [c.id for c in s.state.cards.values() if c.name == 'Trinisphere' and c.owner == 'p1']
    assert len(sphere_ids) == 2
    return s, sphere_ids


@pytest.mark.parametrize('tapped', [(False, False), (True, False), (True, True)])
def test_multiple_spheres_use_one_floor_from_untapped_sources(cards, tapped):
    s, spheres = setup(cards)
    act(s, 'p1', type='move', card_ids=spheres, to={'player': 'p1', 'zone': 'battlefield'})
    for cid, tap in zip(spheres, tapped, strict=True):
        if tap:
            act(s, 'p1', type='tap', card_ids=[cid], tapped=True)
    spell = put(s, 'Lightning Bolt', 'hand')
    mana(s, C=0 if all(tapped) else 2, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


def test_phased_out_sphere_does_not_set_a_floor(cards):
    s, spheres = setup(cards)
    act(s, 'p1', type='move', card_ids=[spheres[0]], to={'player': 'p1', 'zone': 'battlefield'})
    ripple = put(s, 'Reality Ripple', 'hand')
    mana(s, C=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=ripple.id, targets=[spheres[0]])
    settle(s)
    spell = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_losing_and_regaining_the_ability_changes_the_floor(cards):
    s, spheres = setup(cards)
    cid = spheres[0]
    act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'battlefield'})
    ensoul = put(s, 'Ensoul Artifact', 'hand')
    mana(s, C=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=ensoul.id, targets=[cid])
    settle(s)
    mutation = put(s, 'Darksteel Mutation', 'hand')
    mana(s, C=2, W=1)
    act(s, 'p1', type='cast_spell', card_id=mutation.id, targets=[cid])
    settle(s)
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    act(s, 'p1', type='move', card_ids=[mutation.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[bolt.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, C=2, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 34
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)
