"""Held source-damage cohort patch plus exact Spinneret leaf; native gameplay only."""
import inspect

import pytest

from app.rules import exile_damage_choices49 as leaf
from app.rules import scripts, triggers
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

pytestmark=pytest.mark.skipif('source_damage_totals' not in inspect.getsource(triggers._generic_events),reason='Native source-damage cohort proposal isolated pending review')
cards=gameplay.cards


@pytest.fixture(autouse=True)
def staged(monkeypatch):
    native=scripts.define
    monkeypatch.setattr(scripts,'define',lambda ability,ch:leaf.definition(ability,ch) or native(ability,ch))
    scripts._cached.cache_clear()
    yield
    scripts._cached.cache_clear()


def test_spinneret_actual_two_other_spiders_attack_adds_one_counter_with_source_staying_home(cards):
    s=gameplay.setup(cards,'Spinneret and Spiderling','Giant Spider','Giant Spider')
    source=put(s,'Spinneret and Spiderling','battlefield')
    first=put(s,'Giant Spider','battlefield')
    second=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Giant Spider' and c.id!=first.id)
    act(s,'p1',type='move',card_ids=[second.id],to={'zone':'battlefield','player':'p1'})
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':c.id,'target':'p2'} for c in (first,second)])
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+1')==1
    assert s.state.cards[source.id].attacking is None
    assert not s.state.rules.permissions
    roundtrip(s)


def test_spinneret_actual_four_combat_damage_exiles_one_card_and_grants_normal_land_play(cards):
    s=gameplay.setup(cards,'Spinneret and Spiderling','Forest')
    source=put(s,'Spinneret and Spiderling','battlefield')
    to_phase(s,'main1',turn=4)
    cast(s,'Giant Growth',targets=[source.id])
    top=put(s,'Forest','library')
    gameplay.combat_optional_offer(s,source)
    assert s.state.players['p2'].life==36
    assert s.state.cards[top.id].zone=='p1:exile'
    assert len(s.state.rules.permissions)==1
    to_phase(s,'main2',turn=4)
    act(s,'p1',type='play_land',card_id=top.id)
    assert s.state.cards[top.id].zone=='p1:battlefield'
    roundtrip(s)


def test_spinneret_actual_ignition_simultaneous_two_to_each_opponent_qualifies_once(cards):
    s=gameplay.setup(cards,'Spinneret and Spiderling',"Chandra's Ignition",'Forest')
    source=put(s,'Spinneret and Spiderling','battlefield')
    act(s,'p1',type='counter',card_ids=[source.id],kind='+1/+1',delta=1)
    top=put(s,'Forest','library')
    next_top=s.state.zones['p1:library'][1]
    cast(s,"Chandra's Ignition",targets=[source.id])
    assert s.state.players['p2'].life==38 and s.state.players['p3'].life==38
    assert s.state.cards[top.id].zone=='p1:exile'
    assert s.state.cards[next_top].zone=='p1:library'
    assert len(s.state.rules.permissions)==1
    roundtrip(s)


@pytest.mark.parametrize('counters',[0,2])
def test_spinneret_actual_one_or_three_combat_damage_does_not_exile(cards,counters):
    s=gameplay.setup(cards,'Spinneret and Spiderling','Forest')
    source=put(s,'Spinneret and Spiderling','battlefield')
    if counters:
        act(s,'p1',type='counter',card_ids=[source.id],kind='+1/+1',delta=counters)
    to_phase(s,'declare_attackers',turn=4)
    top=put(s,'Forest','library')
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    to_phase(s,'main2',turn=4)
    assert s.state.players['p2'].life==39-counters
    assert s.state.cards[top.id].zone=='p1:library'
    assert not s.state.rules.permissions
    assert s.state.cards[source.id].counters.get('+1/+1',0)==counters
    roundtrip(s)


def test_spinneret_two_separate_actual_source_damage_instructions_are_not_coalesced(cards):
    s=gameplay.setup(cards,'Spinneret and Spiderling',"Soul's Fire","Soul's Fire",'Forest')
    source=put(s,'Spinneret and Spiderling','battlefield')
    act(s,'p1',type='counter',card_ids=[source.id],kind='+1/+1',delta=1)
    top=put(s,'Forest','library')
    first=cast(s,"Soul's Fire",targets=[source.id,'p2'],target_counts=[1,1])
    second=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=="Soul's Fire" and c.id!=first.id)
    act(s,'p1',type='move',card_ids=[second.id],to={'zone':'hand','player':'p1'})
    act(s,'p1',type='cast_spell',card_id=second.id,targets=[source.id,'p2'],target_counts=[1,1])
    settle(s)
    assert s.state.players['p2'].life==36
    assert s.state.cards[top.id].zone=='p1:library'
    assert not s.state.rules.permissions
    roundtrip(s)


def test_spinneret_prevented_four_combat_damage_does_not_exile(cards):
    s=gameplay.setup(cards,'Spinneret and Spiderling','Forest','Fog')
    source=put(s,'Spinneret and Spiderling','battlefield')
    to_phase(s,'main1',turn=4)
    cast(s,'Giant Growth',targets=[source.id])
    cast(s,'Fog')
    top=put(s,'Forest','library')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    to_phase(s,'main2',turn=4)
    assert s.state.players['p2'].life==40
    assert s.state.cards[top.id].zone=='p1:library'
    assert not s.state.rules.permissions
    roundtrip(s)


@pytest.mark.parametrize('expired',[False,True])
def test_spinneret_permission_survives_source_death_through_next_own_turn_then_expires(cards,expired):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import mana

    s=gameplay.setup(cards,'Spinneret and Spiderling',"Chandra's Ignition",'Murder')
    source=put(s,'Spinneret and Spiderling','battlefield')
    act(s,'p1',type='counter',card_ids=[source.id],kind='+1/+1',delta=1)
    top=put(s,'Divination','library')
    cast(s,"Chandra's Ignition",targets=[source.id])
    cast(s,'Murder',targets=[source.id])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    to_phase(s,'main1',turn=7 if expired else 4)
    act(s,'p1',type='clear_mana',player='p1')
    mana(s,U=1,C=2)
    if expired:
        before=s.state.model_dump_json()
        with pytest.raises(ActionError):
            act(s,'p1',type='cast_spell',card_id=top.id)
        assert s.state.model_dump_json()==before
    else:
        act(s,'p1',type='cast_spell',card_id=top.id)
        settle(s)
        assert s.state.cards[top.id].zone=='p1:graveyard'
        assert not s.state.players['p1'].mana
    roundtrip(s)


def test_spinneret_actual_damage_trigger_countered_before_exile_has_no_permission(cards):
    from tests.test_rules_bandmate_references import mana

    s=gameplay.setup(cards,'Spinneret and Spiderling',"Chandra's Ignition",'Stifle','Forest')
    source=put(s,'Spinneret and Spiderling','battlefield')
    act(s,'p1',type='counter',card_ids=[source.id],kind='+1/+1',delta=1)
    top=put(s,'Forest','library')
    spell=put(s,"Chandra's Ignition",'hand')
    mana(s,R=2,C=3)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[source.id])
    for _ in range(12):
        trigger=next((k for k,e in s.state.rules.stack.items() if e.kind=='trigger' and e.source_card==source.id),None)
        if trigger:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert trigger is not None
    cast(s,'Stifle',targets=[trigger])
    assert s.state.cards[top.id].zone=='p1:library'
    assert not s.state.rules.permissions
    roundtrip(s)
