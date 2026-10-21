"""Dependent Equipment targets bind and recheck the earlier creature target."""
import pytest

from app.rules import coverage
from tests import test_rules_fight_exile_receipts65 as support
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_ordered_tutor_continuations import cast


@pytest.fixture()
def cards(settings):
    yield from support.cards.__wrapped__(settings)


setup = support.setup


def test_whole_fiery_canonical(cards):
    assert coverage.of_card_data(cards.resolve('Fiery Annihilation')).level == 'FULL'


def test_fiery_annihilation_no_equipment_still_exiles_lethal_target(cards):
    s = setup(cards)
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Fiery Annihilation', targets=[opposing.id], target_counts=[1, 0])
    assert s.state.cards[opposing.id].zone == 'p2:exile'
    roundtrip(s)



def test_fiery_attached_equipment_is_exiled_with_creature(cards):
    s = setup(cards)
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    equipment = put(s, 'Bonesplitter', 'battlefield', 'p2')
    act(s, 'p2', type='attach', card_ids=[equipment.id], to=opposing.id)
    cast(s, 'Fiery Annihilation', targets=[opposing.id, equipment.id], target_counts=[1, 1])
    assert s.state.cards[opposing.id].zone == 'p2:exile'
    assert s.state.cards[equipment.id].zone == 'p2:exile'
    roundtrip(s)



def test_fiery_illegal_creature_target_preserves_previously_attached_equipment(cards):
    from tests.test_rules_conditional_prevention import cast as pending_cast

    s = setup(cards)
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    equipment = put(s, 'Bonesplitter', 'battlefield', 'p2')
    act(s, 'p2', type='attach', card_ids=[equipment.id], to=opposing.id)
    pending_cast(s, 'Fiery Annihilation', targets=[opposing.id, equipment.id], target_counts=[1, 1], resolve=False)
    pending_cast(s, 'Unsummon', targets=[opposing.id])
    assert s.state.cards[opposing.id].zone == 'p2:hand'
    assert s.state.cards[equipment.id].zone == 'p2:battlefield'
    roundtrip(s)



def test_hexproof_creature_invalidates_dependent_equipment_despite_attachment(cards):
    from tests.test_rules_conditional_prevention import cast as pending_cast

    s = setup(cards)
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    equipment = put(s, 'Bonesplitter', 'battlefield', 'p2')
    act(s, 'p2', type='attach', card_ids=[equipment.id], to=opposing.id)
    pending_cast(s, 'Fiery Annihilation', targets=[opposing.id, equipment.id], target_counts=[1, 1], resolve=False)
    pending_cast(s, 'Blossoming Defense', targets=[opposing.id], pid='p2')
    assert s.state.cards[opposing.id].zone == s.state.cards[equipment.id].zone == 'p2:battlefield'
    assert s.state.cards[equipment.id].attached_to == opposing.id
    assert s.state.cards[opposing.id].damage == 0
    roundtrip(s)


def test_equipment_moved_to_other_creature_is_no_longer_dependent_target(cards):
    from tests.test_rules_conditional_prevention import cast as pending_cast

    s = setup(cards)
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    equipment = put(s, 'Bonesplitter', 'battlefield', 'p2')
    act(s, 'p2', type='attach', card_ids=[equipment.id], to=opposing.id)
    pending_cast(s, 'Fiery Annihilation', targets=[opposing.id, equipment.id], target_counts=[1, 1], resolve=False)
    pending_cast(s, 'Magnetic Theft', targets=[equipment.id, other.id], target_counts=[1, 1], pid='p2', resolve=False)
    from tests.test_rules_copy import resolve_top
    from tests.test_rules_library_look import settle

    resolve_top(s)
    assert s.state.cards[equipment.id].attached_to == other.id
    settle(s)
    assert s.state.cards[opposing.id].zone == 'p2:exile'
    assert s.state.cards[equipment.id].zone == 'p2:battlefield'
    assert s.state.cards[equipment.id].attached_to == other.id
    roundtrip(s)


def test_actual_reverberate_rebinds_equipment_choices_to_new_creature_target(cards):
    from tests.test_rules_conditional_prevention import cast as pending_cast
    from tests.test_rules_library_look import settle

    s = setup(cards)
    first = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    second = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    old_equipment = put(s, 'Bonesplitter', 'battlefield', 'p2')
    new_equipment = put(s, 'Bonesplitter', 'battlefield', 'p3')
    act(s, 'p2', type='attach', card_ids=[old_equipment.id], to=first.id)
    act(s, 'p3', type='attach', card_ids=[new_equipment.id], to=second.id)
    original = pending_cast(s, 'Fiery Annihilation', targets=[first.id, old_equipment.id],
                            target_counts=[1, 1], resolve=False)
    pending_cast(s, 'Reverberate', targets=[original.id])
    d = s.state.rules.decision
    assert d and second.id in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[second.id])
    d = s.state.rules.decision
    assert d and new_equipment.id in [o.id for o in d.options]
    assert old_equipment.id not in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[new_equipment.id])
    settle(s)
    assert s.state.cards[first.id].zone == s.state.cards[old_equipment.id].zone == 'p2:exile'
    assert s.state.cards[second.id].zone == s.state.cards[new_equipment.id].zone == 'p3:exile'
    roundtrip(s)
