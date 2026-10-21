"""CR 120.8, 400.7, 602.5b, 608.2h: Steel Hellkite's damage history."""
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
from tests.test_rules_banding import declare_only
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Steel Hellkite'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/steel_hellkite_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, *, combat=True):
    s = table(cards, [NAME, 'Grizzly Bears', 'Cloudshift', 'Lightning Bolt', "Soul's Fire"],
              ['Grizzly Bears', 'Sol Ring', 'Ornithopter', 'Darksteel Ingot'], ['Grizzly Bears'])
    source = put(s, NAME, 'battlefield')
    own = put(s, 'Grizzly Bears', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    other = put(s, 'Grizzly Bears', 'battlefield', pid='p3')
    ring = put(s, 'Sol Ring', 'battlefield', pid='p2')
    thopter = put(s, 'Ornithopter', 'battlefield', pid='p2')
    land = put(s, 'Island', 'battlefield', pid='p2')
    if combat:
        declare_only(s, [source], [])
        to_phase(s, 'main2', turn=4)
        assert s.state.players['p2'].life == 35
    return s, source, own, bear, other, ring, thopter, land


def activate(s, source, x):
    wait_priority(s, 'p1')
    mana(s, C=x)
    act(s, 'p1', type='activate_ability', card_id=source.id,
        ability=ability_index(s, source, '{X}:'), x_value=x)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('x,dead', [(0,'thopter'), (1,'ring'), (2,'bear'), (3,None)])
def test_exact_mana_value_only_damaged_players_and_never_lands(cards, x, dead):
    s, source, own, bear, other, ring, thopter, land = setup(cards)
    activate(s, source, x)
    roundtrip(s)
    settle(s)
    for name, obj in [('bear',bear), ('ring',ring), ('thopter',thopter)]:
        assert s.state.cards[obj.id].zone == ('p2:graveyard' if name == dead else 'p2:battlefield')
    assert s.state.cards[own.id].zone == 'p1:battlefield'
    assert s.state.cards[other.id].zone == 'p3:battlefield'
    assert s.state.cards[land.id].zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('departure', ['graveyard', 'blink'])
def test_activated_ability_keeps_original_source_damage_history(cards, departure):
    s, source, _, bear, _, _, _, _ = setup(cards)
    activate(s, source, 2)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player':'p1','zone':'graveyard'})
    if departure == 'blink':
        act(s, 'p1', type='move', card_ids=[source.id], to={'player':'p1','zone':'battlefield'})
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_current_controller_determines_destroyed_permanents(cards):
    s, source, _, bear, other, _, _, _ = setup(cards)
    activate(s, source, 2)
    act(s, 'p1', type='set_controller', card_ids=[bear.id], player='p3')
    act(s, 'p1', type='set_controller', card_ids=[other.id], player='p2')
    settle(s)
    assert s.state.cards[bear.id].zone == 'p3:battlefield'
    assert s.state.cards[other.id].zone == 'p3:graveyard'  # owner, not controller
    roundtrip(s)


def test_no_damage_and_previous_turn_damage_do_not_qualify(cards):
    s, source, _, bear, _, _, _, _ = setup(cards, combat=False)
    activate(s, source, 2)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:battlefield'
    to_phase(s, 'main1', turn=4)
    declare_only(s, [source], [])
    to_phase(s, 'main2', turn=4)
    to_phase(s, 'main1', turn=5)
    wait_priority(s, 'p1')
    activate(s, source, 2)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_once_per_turn_even_without_destroying_anything(cards):
    from app.game.errors import ActionError

    s, source, _, _, _, _, _, _ = setup(cards)
    activate(s, source, 3)
    settle(s)
    with pytest.raises(ActionError):
        activate(s, source, 2)
    roundtrip(s)


def test_indestructible_survives_normal_destruction_pipeline(cards):
    s, source, _, _, _, _, _, _ = setup(cards)
    ingot = put(s, 'Darksteel Ingot', 'battlefield', pid='p2')
    activate(s, source, 3)
    settle(s)
    assert s.state.cards[ingot.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_noncombat_damage_from_same_source_does_not_qualify(cards):
    s, source, _, bear, _, _, _, _ = setup(cards, combat=False)
    to_phase(s, 'main1', turn=1)
    spell = put(s, "Soul's Fire", 'hand')
    mana(s, C=2, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id, 'p2'], target_counts=[1,1])
    settle(s)
    assert s.state.players['p2'].life == 35
    activate(s, source, 2)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_blink_before_activation_has_no_old_objects_damage_history(cards):
    s, source, _, bear, _, _, _, _ = setup(cards)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player':'p1','zone':'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player':'p1','zone':'battlefield'})
    activate(s, source, 2)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:battlefield'
    roundtrip(s)
