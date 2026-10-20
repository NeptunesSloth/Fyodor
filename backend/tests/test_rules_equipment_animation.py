"""CR 301.5, 613.1d: Equipment animating planeswalkers and host counters."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/equipment_animation_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = "Luxior, Giada's Gift"


def test_luxior_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, *, counters=4):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Geyadrone Dihada', 'Grizzly Bears', 'Disenchant'], ['Grizzly Bears', 'Geyadrone Dihada', 'Lightning Bolt'])
    source = put(s, NAME, 'battlefield')
    walker = put(s, 'Geyadrone Dihada', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=counters)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    return s, source, walker, bear


def equip(s, source, target, *, walker=True):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_wave7b_activation import ability_index

    wait_priority(s, 'p1')
    mana(s, C=1 if walker else 3)
    act(s, 'p1', type='activate_ability', card_id=source.id,
        ability=ability_index(s, source, 'Equip planeswalker' if walker else 'Equip {3}'), targets=[target.id])
    settle(s)


def test_equip_planeswalker_animates_retains_loyalty_and_can_activate_abilities(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, source, walker, bear = setup(cards)
    equip(s, source, walker)
    assert s.state.cards[source.id].attached_to == walker.id
    assert chars(s, walker).types == frozenset({'Creature'})
    assert chars(s, walker).pt == (4, 4)
    assert s.state.cards[walker.id].counters['loyalty'] == 4
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=1, targets=[bear.id], target_counts=[1])
    settle(s)
    assert chars(s, walker).pt == (5, 5) and s.state.cards[walker.id].counters['loyalty'] == 5
    roundtrip(s)


def test_pump_counts_all_host_counters_and_never_equipment_counters(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, source, walker, _ = setup(cards)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='charge', value=20)
    equip(s, source, walker)
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='charge', value=2)
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='+1/+1', value=3)
    # Nine counters grant +9/+9; the three +1/+1 counters themselves add +3/+3.
    assert chars(s, walker).pt == (12, 12)
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='charge', value=0)
    assert chars(s, walker).pt == (10, 10)
    roundtrip(s)


def test_regular_equip_retargets_to_creature_and_restores_old_planeswalker(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, source, walker, bear = setup(cards)
    equip(s, source, walker)
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='charge', value=2)
    equip(s, source, bear, walker=False)
    assert s.state.cards[source.id].attached_to == bear.id
    assert chars(s, walker).types == frozenset({'Planeswalker'})
    assert chars(s, bear).pt == (4, 4)
    roundtrip(s)


def test_destroying_equipment_restores_planeswalker_with_its_counters(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, source, walker, _ = setup(cards)
    equip(s, source, walker)
    wait_priority(s, 'p1')
    disenchant = put(s, 'Disenchant', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=disenchant.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert chars(s, walker).types == frozenset({'Planeswalker'})
    assert s.state.cards[walker.id].counters['loyalty'] == 4
    roundtrip(s)


def test_zero_counter_animated_planeswalker_dies_as_zero_zero(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, source, walker, _ = setup(cards)
    equip(s, source, walker)
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=0)
    act(s, s.state.rules.priority, type='pass_priority')
    settle(s)
    assert s.state.cards[walker.id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].attached_to is None
    roundtrip(s)


def test_equip_planeswalker_rejects_nonplaneswalker_creature(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave7b_activation import ability_index

    s, source, _, bear = setup(cards)
    mana(s, C=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id,
            ability=ability_index(s, source, 'Equip planeswalker'), targets=[bear.id])
    assert s.state.players['p1'].mana['C'] == 1
    roundtrip(s)


def test_damage_to_animated_planeswalker_does_not_remove_loyalty(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, source, walker, _ = setup(cards)
    equip(s, source, walker)
    wait_priority(s, 'p2')
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    mana(s, pid='p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=[walker.id])
    settle(s)
    assert s.state.cards[walker.id].zone == 'p1:battlefield'
    assert s.state.cards[walker.id].counters['loyalty'] == 4
    assert s.state.cards[walker.id].damage == 3
    roundtrip(s)


def test_equip_planeswalker_cannot_target_opponents_planeswalker(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave7b_activation import ability_index

    s, source, _, _ = setup(cards)
    opposing = put(s, 'Geyadrone Dihada', 'battlefield', pid='p2')
    act(s, 'p2', type='set_counter', card_id=opposing.id, kind='loyalty', value=4)
    mana(s, C=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id,
            ability=ability_index(s, source, 'Equip planeswalker'), targets=[opposing.id])
    assert s.state.players['p1'].mana['C'] == 1 and s.state.cards[source.id].attached_to is None
    roundtrip(s)
