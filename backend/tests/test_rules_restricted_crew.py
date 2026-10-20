"""CR 602.5b, 702.122: restrictions on a crew ability."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/restricted_crew_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Luxurious Locomotive'


def test_locomotive_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup_vehicle(cards, name=NAME, *, turn=1):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [name, 'Grizzly Bears', 'Llanowar Elves'], ['Grizzly Bears', 'Stifle'])
    source = put(s, name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=turn)
    return s, source, bear, elf, other, ability_index(s, source, 'Crew 1')


def crew(s, source, index, picked):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    act(s, source.controller, type='activate_ability', card_id=source.id, ability=index, crew=[c.id for c in picked])
    settle(s)


def test_second_crew_is_rejected_and_disappears_from_available_actions(cards):
    from app.game.errors import ActionError
    from app.rules.casting import activatable
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, source, bear, elf, _, index = setup_vehicle(cards)
    assert {'card_id': source.id, 'ability': index} in activatable(s.state, 'p1', s.cards, check_priority=False)
    crew(s, source, index, [bear])
    roundtrip(s)
    assert {'card_id': source.id, 'ability': index} not in activatable(s.state, 'p1', s.cards, check_priority=False)
    with pytest.raises(ActionError, match='once|already'):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[elf.id])
    assert not s.state.cards[elf.id].tapped
    roundtrip(s)


def test_failed_cost_does_not_consume_the_activation(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, source, bear, _, _, index = setup_vehicle(cards)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[])
    crew(s, source, index, [bear])
    assert s.state.cards[bear.id].tapped
    roundtrip(s)


def test_usage_belongs_to_the_object_after_a_control_change(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_designations import roundtrip

    s, source, bear, _, other, index = setup_vehicle(cards)
    crew(s, source, index, [bear])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    wait_priority(s, 'p2')
    with pytest.raises(ActionError, match='once|already'):
        act(s, 'p2', type='activate_ability', card_id=source.id, ability=index, crew=[other.id])
    assert not s.state.cards[other.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('reset', ['turn', 'blink'])
def test_next_turn_or_new_object_can_crew_again(cards, reset):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, source, bear, elf, _, index = setup_vehicle(cards)
    crew(s, source, index, [bear])
    if reset == 'blink':
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    else:
        to_phase(s, 'main1', turn=2)
        wait_priority(s, 'p1')
    roundtrip(s)
    crew(s, source, index, [elf])
    assert s.state.cards[elf.id].tapped
    roundtrip(s)


def test_countering_the_crew_ability_still_consumes_its_use(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, source, bear, elf, _, index = setup_vehicle(cards)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[bear.id])
    ability = s.state.zones['stack'][-1]
    wait_priority(s, 'p2')
    stifle = put(s, 'Stifle', 'hand', 'p2')
    mana(s, 'p2', U=1)
    act(s, 'p2', type='cast_spell', card_id=stifle.id, targets=[ability])
    settle(s)
    assert not chars(s, source).is_creature
    roundtrip(s)
    with pytest.raises(ActionError, match='once|already'):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[elf.id])
    assert not s.state.cards[elf.id].tapped
    roundtrip(s)


def test_attack_creates_treasure_for_each_creature_that_paid_the_single_crew(cards):
    from tests.test_rules_banding import declare_only
    from tests.test_rules_designations import roundtrip, settle

    s, source, bear, elf, _, index = setup_vehicle(cards, turn=4)
    crew(s, source, index, [bear, elf])
    declare_only(s, [source], {})
    settle(s)
    treasures = [c for c in s.state.cards.values() if c.is_token and c.name == 'Treasure' and c.controller == 'p1']
    assert len(treasures) == 2
    roundtrip(s)


def test_unrestricted_crew_can_still_activate_twice_in_a_turn(cards):
    from tests.test_rules_designations import roundtrip

    s, source, bear, elf, _, index = setup_vehicle(cards, "Smuggler's Copter")
    crew(s, source, index, [bear])
    crew(s, source, index, [elf])
    assert s.state.cards[bear.id].tapped and s.state.cards[elf.id].tapped
    roundtrip(s)
