"""Dragonfire Blade uses current target colors for cost and source colors for hexproof."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index

NAME = 'Dragonfire Blade'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/dragonfire_blade_cards.json').read_text())
    for i, c in enumerate(rows):
        base[c['name']] = card(c['name'], set_code='dfb', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name='Grizzly Bears'):
    s = table(cards, [NAME, 'Grizzly Bears', 'Baleful Strix', 'Transguild Courier', 'Myr Retriever'],
              ['Lightning Bolt', 'Terminate', 'Disenchant', 'Ghostfire'])
    blade = put(s, NAME, 'battlefield')
    host = put(s, name, 'battlefield')
    return s, blade, host


def equip(s, blade, host, cost):
    if cost:
        act(s, 'p1', type='add_mana', player='p1', mana={'C': cost})
    act(s, 'p1', type='activate_ability', card_id=blade.id, ability=ability_index(s, blade, 'Equip {4}'), targets=[host.id])
    assert mana_pool(s, 'p1') == {}
    settle(s)
    assert s.state.cards[blade.id].attached_to == host.id


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('name,cost', [('Grizzly Bears', 3), ('Baleful Strix', 2), ('Transguild Courier', 0), ('Myr Retriever', 4)])
def test_equip_cost_uses_all_current_target_colors_and_floors_at_zero(cards, name, cost):
    s, blade, host = setup(cards, name)
    equip(s, blade, host, cost)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[host.id])
    assert 'hexproof from' in ch.keywords
    roundtrip(s)


def test_five_color_unchosen_creature_does_not_discount_colorless_target(cards):
    s, blade, host = setup(cards, 'Myr Retriever')
    put(s, 'Transguild Courier', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=blade.id, ability=ability_index(s, blade, 'Equip {4}'), targets=[host.id])
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize('spell,mana,blocked', [('Lightning Bolt', {'R': 1}, True),
                                              ('Terminate', {'B': 1, 'R': 1}, False),
                                              ('Ghostfire', {'C': 2, 'R': 1}, False)])
def test_hexproof_checks_spell_current_colors_including_colorless_despite_red_mana_cost(cards, spell, mana, blocked):
    from tests.test_rules_bandmate_references import wait_priority

    s, blade, host = setup(cards)
    equip(s, blade, host, 3)
    source = put(s, spell, 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana=mana)
    wait_priority(s, 'p2')
    if blocked:
        with pytest.raises(ActionError):
            act(s, 'p2', type='cast_spell', card_id=source.id, targets=[host.id])
        assert s.state.cards[source.id].zone == 'p2:hand'
    else:
        act(s, 'p2', type='cast_spell', card_id=source.id, targets=[host.id])
        settle(s)
        assert s.state.cards[host.id].zone == ('p1:graveyard' if spell == 'Terminate' else 'p1:battlefield')
    roundtrip(s)


def test_destroying_equipment_removes_hexproof_and_bonus_immediately(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s, blade, host = setup(cards)
    equip(s, blade, host, 3)
    disenchant = put(s, 'Disenchant', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 1, 'W': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=disenchant.id, targets=[blade.id])
    settle(s)
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=[host.id])
    settle(s)
    assert s.state.cards[blade.id].zone == 'p1:graveyard'
    assert s.state.cards[host.id].zone == 'p1:graveyard'
    roundtrip(s)
