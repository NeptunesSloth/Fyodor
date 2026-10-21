"""Liliana's nested-quotation emblem grants an additional mana ability to Swamps."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import characteristics
from app.rules.layers import derive
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index

NAME = 'Liliana of the Dark Realms'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/liliana_dark_realms_cards.json').read_text())
    for i, c in enumerate(rows):
        base[c['name']] = card(c['name'], set_code='ldr', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, [NAME, 'Swamp', 'Forest', 'Urborg, Tomb of Yawgmoth', 'Blood Moon'], ['Swamp'])
    source = put(s, NAME, 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=6)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'You get an emblem'))
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert any(c.zone == 'p1:command' and c.token and c.token.type_line == 'Emblem' for c in s.state.cards.values())
    return s


def abilities(s, c, cards):
    return derive(s.state, c, characteristics.of(c, cards), cards).abilities


def tap_four(s, c, cards):
    a = next(a for a in abilities(s, c, cards) if 'Add {B}{B}{B}{B}' in a.text)
    act(s, 'p1', type='activate_ability', card_id=c.id, ability=a.index)


def test_basic_swamp_retains_intrinsic_ability_and_gains_four_black(cards):
    s = setup(cards)
    swamp = put(s, 'Swamp', 'battlefield')
    assert len([a for a in abilities(s, swamp, cards) if a.kind == 'mana']) == 2
    tap_four(s, swamp, cards)
    assert mana_pool(s, 'p1') == {'B': 4}
    assert not s.state.zones['stack']
    roundtrip(s)


def test_only_controlled_swamps_gain_ability(cards):
    s = setup(cards)
    forest = put(s, 'Forest', 'battlefield')
    enemy = put(s, 'Swamp', 'battlefield', pid='p2')
    assert all('Add {B}{B}{B}{B}' not in a.text for c in (forest, enemy) for a in abilities(s, c, cards))
    roundtrip(s)


def test_urborg_makes_nonbasic_land_eligible_and_blood_moon_removes_swamp_type(cards):
    s = setup(cards)
    urborg = put(s, 'Urborg, Tomb of Yawgmoth', 'battlefield')
    tap_four(s, urborg, cards)
    assert mana_pool(s, 'p1') == {'B': 4}
    put(s, 'Blood Moon', 'battlefield')
    assert all('Add {B}{B}{B}{B}' not in a.text for a in abilities(s, urborg, cards))
    roundtrip(s)


def test_grant_follows_current_controller_and_does_not_change_ownership(cards):
    s = setup(cards)
    swamp = put(s, 'Swamp', 'battlefield', pid='p2')
    act(s, 'p1', type='set_controller', card_ids=[swamp.id], player='p1')
    swamp = s.state.cards[swamp.id]
    assert swamp.owner == 'p2'
    tap_four(s, swamp, cards)
    assert mana_pool(s, 'p1') == {'B': 4}
    act(s, 'p1', type='set_controller', card_ids=[swamp.id], player='p2')
    assert all('Add {B}{B}{B}{B}' not in a.text for a in abilities(s, s.state.cards[swamp.id], cards))
    roundtrip(s)
