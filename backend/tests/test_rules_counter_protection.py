"""CR 702.16: protection from permanents with specified counters."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/counter_protection_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Geyadrone Dihada'


def test_dihada_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, *, source_owner='p2', corruption=1):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, [NAME, 'Vulshok Sorcerer', 'Lightning Bolt', 'Murder', 'Sarkhan the Masterless', 'Basilisk Collar'],
              ['Vulshok Sorcerer', 'Grizzly Bears', 'Lightning Bolt', 'Wind Drake'])
    target = put(s, NAME, 'battlefield')
    act(s, 'p1', type='set_counter', card_id=target.id, kind='loyalty', value=10)
    source = put(s, 'Vulshok Sorcerer', 'battlefield', pid=source_owner)
    if corruption:
        act(s, source_owner, type='set_counter', card_id=source.id, kind='corruption', value=corruption)
    return s, target, source, ability_index(s, source, 'deals')


@pytest.mark.parametrize('owner', ['p1', 'p2'])
def test_corrupted_permanent_cannot_target_even_its_controllers_dihada(cards, owner):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_designations import roundtrip

    s, target, source, index = setup(cards, source_owner=owner)
    wait_priority(s, owner)
    with pytest.raises(ActionError):
        act(s, owner, type='activate_ability', card_id=source.id, ability=index, targets=[target.id])
    assert not s.state.cards[source.id].tapped
    assert s.state.cards[target.id].counters['loyalty'] == 10
    roundtrip(s)


@pytest.mark.parametrize('kind', ['corruption', '+1/+1'])
def test_live_counter_kind_and_removal_determine_protection(cards, kind):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, target, source, index = setup(cards)
    act(s, 'p2', type='set_counter', card_id=source.id, kind='corruption', value=0)
    if kind != 'corruption':
        act(s, 'p2', type='set_counter', card_id=source.id, kind=kind, value=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=index, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].counters['loyalty'] == 9
    roundtrip(s)


def test_instant_spell_is_not_a_protected_permanent_source(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, target, _, _ = setup(cards)
    wait_priority(s, 'p2')
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    mana(s, pid='p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].counters['loyalty'] == 7
    roundtrip(s)


@pytest.mark.parametrize('leave', [False, True])
def test_target_recheck_uses_current_or_last_known_corruption(cards, leave):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, target, source, index = setup(cards, corruption=0)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=index, targets=[target.id])
    act(s, 'p2', type='set_counter', card_id=source.id, kind='corruption', value=1)
    if leave:
        wait_priority(s, 'p1')
        murder = put(s, 'Murder', 'hand')
        mana(s, C=1, B=2)
        act(s, 'p1', type='cast_spell', card_id=murder.id, targets=[source.id])
    roundtrip(s)
    settle(s)
    assert s.state.cards[target.id].counters['loyalty'] == 10
    assert s.state.cards[source.id].zone == ('p2:graveyard' if leave else 'p2:battlefield')
    roundtrip(s)


@pytest.mark.parametrize('corruption', [0, 1])
def test_corrupted_attacker_can_attack_but_combat_damage_is_prevented(cards, corruption):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, target, _, _ = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    if corruption:
        act(s, 'p2', type='set_counter', card_id=bear.id, kind='corruption', value=corruption)
    to_phase(s, 'declare_attackers', turn=2)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': target.id}])
    settle(s)
    to_phase(s, 'end_combat', turn=2)
    assert s.state.cards[target.id].counters['loyalty'] == (10 if corruption else 8)
    roundtrip(s)


def test_real_loyalty_ability_marks_a_creature_and_turns_on_protection(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, target, source, index = setup(cards, corruption=0)
    life = {p: s.state.players[p].life for p in s.state.players}
    act(s, 'p1', type='activate_ability', card_id=target.id, ability=1, targets=[source.id], target_counts=[1])
    settle(s)
    assert s.state.cards[source.id].counters['corruption'] == 1
    assert s.state.players['p1'].life == life['p1'] + 2
    assert all(s.state.players[p].life == life[p] - 2 for p in ['p2', 'p3'])
    wait_priority(s, 'p2')
    with pytest.raises(ActionError):
        act(s, 'p2', type='activate_ability', card_id=source.id, ability=index, targets=[target.id])
    roundtrip(s)


def animate_dihada(s, target):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put
    from tests.test_rules_wave7b_activation import ability_index

    sarkhan = put(s, 'Sarkhan the Masterless', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=sarkhan.id, kind='loyalty', value=5)
    act(s, 'p1', type='activate_ability', card_id=sarkhan.id, ability=ability_index(s, sarkhan, '+1:'))
    settle(s)
    wait_priority(s, 'p1')
    equipment = put(s, 'Basilisk Collar', 'battlefield')
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=equipment.id,
        ability=ability_index(s, equipment, 'Equip {2}'), targets=[target.id])
    settle(s)
    return equipment


def test_corrupted_equipment_falls_off_animated_dihada(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, target, _, _ = setup(cards)
    equipment = animate_dihada(s, target)
    assert s.state.cards[equipment.id].attached_to == target.id
    assert chars(s, target).is_creature and 'Planeswalker' not in chars(s, target).types
    act(s, 'p1', type='set_counter', card_id=equipment.id, kind='corruption', value=1)
    act(s, s.state.rules.priority, type='pass_priority')
    settle(s)
    assert s.state.cards[equipment.id].attached_to is None
    assert chars(s, target).is_creature and 'lifelink' not in chars(s, target).keywords
    roundtrip(s)


@pytest.mark.parametrize('corruption', [0, 1])
def test_corrupted_creature_cannot_block_animated_dihada(cards, corruption):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_banding import declare_only, until_block
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, target, _, _ = setup(cards)
    to_phase(s, 'main1', turn=4)
    animate_dihada(s, target)
    blocker = put(s, 'Wind Drake', 'battlefield', pid='p2')
    if corruption:
        act(s, 'p2', type='set_counter', card_id=blocker.id, kind='corruption', value=1)
    declare_only(s, [target], [])
    until_block(s)
    if corruption:
        with pytest.raises(ActionError):
            act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': target.id}])
        act(s, 'p2', type='declare_blockers', blocks=[])
    else:
        act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': target.id}])
    roundtrip(s)
