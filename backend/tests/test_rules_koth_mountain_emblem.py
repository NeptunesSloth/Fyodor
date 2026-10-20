"""Canonical Koth ultimate grants targeted stack abilities to current Mountains."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/koth_mountain_emblem_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()





def setup(cards):
    from tests.test_rules_wave7b_activation import ability_index
    s = table(cards, ['Koth of the Hammer', 'Mountain', 'Forest', 'Prismatic Omen'], ['Mountain', 'Stifle'], ['Grizzly Bears'])
    source = put(s, 'Koth of the Hammer', 'hand')
    mountain = put(s, 'Mountain', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 2, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert s.state.cards[source.id].counters.get('loyalty') == 3
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=5)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'You get an emblem'))
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert len([c for c in s.state.cards.values() if c.zone == 'p1:command' and c.token and c.token.type_line == 'Emblem']) == 1
    roundtrip(s)
    return s, source, mountain


def damage_index(s, land):
    from tests.test_rules_wave7b_activation import ability_index
    return ability_index(s, land, 'deals 1 damage')


def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Koth of the Hammer')).level == 'FULL'


def test_actual_ultimate_persists_after_koth_dies_and_damage_uses_stack(cards):
    from tests.game_helpers import mana_pool
    s, _, mountain = setup(cards)
    act(s, 'p1', type='activate_ability', card_id=mountain.id, ability=damage_index(s, mountain), targets=['p2'])
    assert s.state.cards[mountain.id].tapped
    assert s.state.players['p2'].life == 40
    assert s.state.rules.stack
    assert not mana_pool(s)
    roundtrip(s)
    settle(s)
    assert s.state.players['p2'].life == 39
    roundtrip(s)


def test_mountain_still_has_distinct_intrinsic_red_mana_ability(cards):
    from tests.game_helpers import mana_pool
    from tests.test_rules_wave7b_activation import ability_index
    s, _, mountain = setup(cards)
    act(s, 'p1', type='activate_ability', card_id=mountain.id, ability=ability_index(s, mountain, 'Add {R}'))
    assert mana_pool(s).get('R') == 1
    assert not s.state.rules.stack
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_newly_gained_mountain_type_gets_grant_and_losing_type_removes_it(cards):
    s, _, _ = setup(cards)
    forest = put(s, 'Forest', 'battlefield')
    omen = put(s, 'Prismatic Omen', 'battlefield')
    index = damage_index(s, forest)
    act(s, 'p1', type='activate_ability', card_id=forest.id, ability=index, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 39
    act(s, 'p1', type='move', card_ids=[omen.id], to={'player': 'p1', 'zone': 'graveyard'})
    with pytest.raises(StopIteration):
        damage_index(s, forest)
    roundtrip(s)


def test_grant_uses_current_controller_of_mountains(cards):
    s, _, mountain = setup(cards)
    theirs = put(s, 'Mountain', 'battlefield', pid='p2')
    with pytest.raises(StopIteration):
        damage_index(s, theirs)
    act(s, 'p2', type='set_controller', card_ids=[theirs.id], player='p1')
    assert damage_index(s, theirs) >= 0
    act(s, 'p1', type='set_controller', card_ids=[mountain.id], player='p2')
    with pytest.raises(StopIteration):
        damage_index(s, mountain)
    roundtrip(s)


def test_granted_targeted_ability_can_be_countered_by_stifle(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s, _, mountain = setup(cards)
    act(s, 'p1', type='activate_ability', card_id=mountain.id, ability=damage_index(s, mountain), targets=['p2'])
    ability = next(iter(s.state.rules.stack))
    spell = put(s, 'Stifle', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[ability], sources=[])
    settle(s)
    assert s.state.players['p2'].life == 40
    assert s.state.cards[mountain.id].tapped
    roundtrip(s)
