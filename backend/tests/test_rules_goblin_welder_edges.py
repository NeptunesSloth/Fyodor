"""CR 400.7, 603.10, 608.2b, 614.12: simultaneous Welder edges."""
from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_conditionals import settle as choose_all
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_goblin_welder import activate, setup
from tests.test_rules_goblin_welder import cards as cards


def test_outgoing_cage_still_blocks_the_simultaneously_returning_creature(cards):
    s,welder,outgoing,incoming=setup(cards,out="Grafdigger's Cage",incoming='Ornithopter')
    activate(s,welder,outgoing,incoming)
    settle(s)
    assert s.state.cards[outgoing.id].zone=='p1:graveyard'
    assert s.state.cards[incoming.id].zone=='p1:graveyard'
    roundtrip(s)


def test_outgoing_cage_does_not_block_a_noncreature_artifact_return(cards):
    s,welder,outgoing,incoming=setup(cards,out="Grafdigger's Cage",incoming="Investigator's Journal")
    activate(s,welder,outgoing,incoming)
    settle(s)
    assert s.state.cards[outgoing.id].zone=='p1:graveyard'
    assert s.state.cards[incoming.id].zone=='p1:battlefield'
    assert s.state.cards[incoming.id].counters.get('suspect')==1  # Welder
    roundtrip(s)


def test_journal_entry_count_includes_the_creature_leaving_in_the_same_event(cards):
    s,welder,outgoing,incoming=setup(cards,out='Ornithopter',incoming="Investigator's Journal")
    activate(s,welder,outgoing,incoming)
    settle(s)
    assert s.state.cards[outgoing.id].zone=='p1:graveyard'
    assert s.state.cards[incoming.id].zone=='p1:battlefield'
    assert s.state.cards[incoming.id].counters.get('suspect')==2  # Welder + outgoing Ornithopter, before the event
    roundtrip(s)


def test_stolen_artifact_uses_controllers_graveyard_but_dies_to_owners_graveyard(cards):
    s,welder,outgoing,_=setup(cards)
    incoming=put(s,'Ornithopter','graveyard',pid='p2')
    act(s,'p1',type='set_controller',card_ids=[outgoing.id],player='p2')
    activate(s,welder,outgoing,incoming)
    settle(s)
    assert s.state.cards[outgoing.id].zone=='p1:graveyard'
    assert s.state.cards[incoming.id].zone=='p2:battlefield'
    assert s.state.cards[incoming.id].controller=='p2' and s.state.cards[incoming.id].owner=='p2'
    roundtrip(s)


@pytest.mark.parametrize('pid,new_controller',[('p1','p2'),('p2','p1'),('p2','p3')])
def test_control_change_invalidates_graveyard_dependency_and_prevents_both_actions(cards,pid,new_controller):
    s,welder,outgoing,incoming=setup(cards,pid=pid)
    activate(s,welder,outgoing,incoming)
    act(s,'p1',type='set_controller',card_ids=[outgoing.id],player=new_controller)
    settle(s)
    assert s.state.cards[outgoing.id].zone==new_controller+':battlefield'
    assert s.state.cards[incoming.id].zone==pid+':graveyard'
    roundtrip(s)


@pytest.mark.parametrize('blink',['outgoing','incoming'])
def test_target_leaving_and_returning_to_the_same_zone_is_a_new_illegal_object(cards,blink):
    s,welder,outgoing,incoming=setup(cards)
    activate(s,welder,outgoing,incoming)
    target=outgoing if blink=='outgoing' else incoming
    zone='battlefield' if blink=='outgoing' else 'graveyard'
    act(s,'p1',type='move',card_ids=[target.id],to={'player':'p1','zone':'exile'})
    act(s,'p1',type='move',card_ids=[target.id],to={'player':'p1','zone':zone})
    settle(s)
    assert s.state.cards[outgoing.id].zone=='p1:battlefield'
    assert s.state.cards[incoming.id].zone=='p1:graveyard'
    roundtrip(s)


def test_outgoing_death_trigger_selects_targets_from_the_completed_simultaneous_event(cards):
    s,welder,outgoing,incoming=setup(cards,out='Scrap Trawler',incoming='Myr Retriever')
    egg=put(s,'Golden Egg','graveyard')
    activate(s,welder,outgoing,incoming)
    # The outgoing Trawler's death trigger exists, but the returning Retriever
    # has already left the graveyard when its target is chosen (603.3d).
    settle(s)
    assert s.state.cards[outgoing.id].zone=='p1:graveyard'
    assert s.state.cards[incoming.id].zone=='p1:battlefield'
    d=s.state.rules.decision
    if d is not None:
        assert egg.id in {o.id for o in d.options}
        assert incoming.id not in {o.id for o in d.options}
    roundtrip(s)
    choose_all(s)
    assert s.state.cards[egg.id].zone=='p1:hand'
    assert s.state.cards[incoming.id].zone=='p1:battlefield'
    roundtrip(s)


def test_artifact_type_from_outgoing_mycosynth_qualifies_the_returning_card(cards):
    s,welder,outgoing,incoming=setup(cards,out='Encroaching Mycosynth',incoming='Marionette Master')
    activate(s,welder,outgoing,incoming)
    choose_all(s)
    assert s.state.cards[outgoing.id].zone=='p1:graveyard'
    assert s.state.cards[incoming.id].zone=='p1:battlefield'
    # The incoming Master didn't witness the outgoing artifact die (603.10).
    assert s.state.players['p2'].life==40 and s.state.players['p3'].life==40
    roundtrip(s)


def test_outgoing_torpor_orb_no_longer_suppresses_the_simultaneous_entry_trigger(cards):
    s,welder,outgoing,incoming=setup(cards,out='Torpor Orb',incoming='Skyscanner')
    hand=len(s.state.zones['p1:hand'])
    activate(s,welder,outgoing,incoming)
    choose_all(s)
    assert s.state.cards[outgoing.id].zone=='p1:graveyard'
    assert s.state.cards[incoming.id].zone=='p1:battlefield'
    assert len(s.state.zones['p1:hand'])==hand+1
    roundtrip(s)


def test_outgoing_entry_watcher_does_not_see_the_artifact_enter_after_it_leaves(cards):
    s,welder,outgoing,incoming=setup(cards,out='Reckless Fireweaver',incoming='Golden Egg',extras=('Mycosynth Lattice',))
    hand=len(s.state.zones['p1:hand'])
    activate(s,welder,outgoing,incoming)
    choose_all(s)
    assert s.state.cards[outgoing.id].zone=='p1:graveyard'
    assert s.state.cards[incoming.id].zone=='p1:battlefield'
    assert len(s.state.zones['p1:hand'])==hand+1  # Golden Egg's own ETB still triggers
    assert s.state.players['p2'].life==40 and s.state.players['p3'].life==40
    roundtrip(s)


def test_outgoing_creature_still_has_its_own_death_trigger(cards):
    s,welder,outgoing,incoming=setup(cards,out='Solemn Simulacrum',incoming='Torpor Orb')
    hand=len(s.state.zones['p1:hand'])
    activate(s,welder,outgoing,incoming)
    choose_all(s)
    assert s.state.cards[outgoing.id].zone=='p1:graveyard'
    assert s.state.cards[incoming.id].zone=='p1:battlefield'
    assert len(s.state.zones['p1:hand'])==hand+1
    roundtrip(s)


def test_welder_can_target_and_sacrifice_itself_when_it_is_an_artifact(cards):
    s,welder,_,incoming=setup(cards,extras=('Mycosynth Lattice',))
    activate(s,welder,welder,incoming)
    settle(s)
    assert s.state.cards[welder.id].zone=='p1:graveyard'
    assert s.state.cards[incoming.id].zone=='p1:battlefield'
    roundtrip(s)


def test_incoming_from_anywhere_graveyard_watcher_sees_the_land_move(cards):
    s,welder,outgoing,incoming=setup(cards,out='Darksteel Citadel',incoming='The Gitrog Monster',extras=('Encroaching Mycosynth',))
    hand=len(s.state.zones['p1:hand'])
    activate(s,welder,outgoing,incoming)
    choose_all(s)
    assert s.state.cards[outgoing.id].zone=='p1:graveyard'
    assert s.state.cards[incoming.id].zone=='p1:battlefield'
    # A from-anywhere graveyard trigger looks at the table after the event,
    # unlike a dies trigger (603.6c / 603.10a).
    assert len(s.state.zones['p1:hand'])==hand+1
    roundtrip(s)
