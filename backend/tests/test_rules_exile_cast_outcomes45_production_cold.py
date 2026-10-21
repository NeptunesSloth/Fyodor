"""Admitted45 native fresh-process cases; no source adapters in either process."""
import pytest

from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_exile_outcomes42_cold import fresh
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase

cards=gameplay.cards



def test_mindclaw_cold_public_reveal_to_foreign_hand_cast_keeps_exact_owner_and_zone(cards,tmp_path):
    from tests.test_rules_ordered_tutor_continuations import cast

    s=gameplay.setup(cards,'Mindclaw Shaman')
    foreign=put(s,'Divination','hand',pid='p2')
    cast(s,'Mindclaw Shaman')
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'target.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['p2']})
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    s=fresh(s,cards,tmp_path/'cast.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[foreign.id]})
    assert s.state.cards[foreign.id].zone=='p2:graveyard'


def test_great_intelligence_cold_opponent_choice_then_free_spell_preserves_draws(cards,tmp_path):
    from tests.test_rules_ordered_tutor_continuations import cast

    s=gameplay.setup(cards,"Great Intelligence's Plan")
    bear=put(s,'Grizzly Bears','hand')
    before=len(s.state.zones['p1:hand'])
    cast(s,"Great Intelligence's Plan",targets=['p2'])
    d=s.state.rules.decision
    assert d.player=='p2' and len(s.state.zones['p1:hand'])==before+3
    s=fresh(s,cards,tmp_path/'choice.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['cast']})
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'free.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[bear.id]})
    assert s.state.cards[bear.id].zone=='p1:battlefield'


@pytest.mark.parametrize('name',['Reinterpret','Press the Enemy'])
def test_counter_or_bounce_cold_frozen_announced_x_after_target_left_stack(cards,tmp_path,name):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_ordered_tutor_continuations import cast

    s=gameplay.setup(cards,name,'Earthquake')
    to_phase(s,'main1',turn=2)
    target=put(s,'Earthquake','hand',pid='p2')
    mana(s,R=1,C=3,pid='p2')
    act(s,'p2',type='set_prefs',hold_priority=True)
    act(s,'p2',type='cast_spell',card_id=target.id,x_value=3)
    for _ in range(3):
        if s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    spell=put(s,'Divination','hand')
    cast(s,name,targets=[target.id])
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    assert d.resume['e']['mv']==4
    s=fresh(s,cards,tmp_path/'frozen.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[spell.id]})
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    assert s.state.cards[target.id].zone==('p2:hand' if name=='Press the Enemy' else 'p2:graveyard')


def test_geode_cold_actual_commander_tax_payment_survives_both_resolution_and_mana_choices(cards,tmp_path):
    from tests.test_rules_bandmate_references import mana

    s=gameplay.setup(cards,'Geode Golem')
    commander=put(s,'Rivaz of the Claw','command')
    act(s,'p1',type='set_commander',card_id=commander.id)
    mana(s,C=1,B=1,R=1)
    act(s,'p1',type='cast_spell',card_id=commander.id)
    settle(s)
    commander=put(s,'Rivaz of the Claw','command')
    source=put(s,'Geode Golem','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    gameplay.geode_offer(s,source)
    act(s,'p1',type='set_prefs',payment='self')
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'commander.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[commander.id]})
    d=s.state.rules.decision
    assert d.resume['step']=='pay_mana'
    mana(s,C=2)
    s=fresh(s,cards,tmp_path/'tax.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['pay']})
    assert s.state.cards[commander.id].zone=='p1:battlefield'
    assert not any(s.state.players['p1'].mana.values())


def test_extract_cold_actual_owner_then_private_caster_then_foreign_spell_cast(cards,tmp_path):
    s,hand=gameplay.extract_ready(cards,['Grizzly Bears','Divination'],1)
    chosen,hidden=hand
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'owner.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[chosen.id]})
    d=s.state.rules.decision
    assert d.player=='p1' and d.resume['stage']=='view'
    assert s.view('p1')['cards'][chosen.id]['name']=='Grizzly Bears'
    assert 'name' not in s.view('p1')['cards'].get(hidden.id,{})
    s=fresh(s,cards,tmp_path/'view.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['ok']})
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'cast.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[chosen.id]})
    assert s.state.cards[chosen.id].zone=='p1:battlefield'
    assert not s.state.cards[chosen.id].revealed_to
    assert s.state.cards[hidden.id].zone=='p2:hand' and not s.state.cards[hidden.id].revealed_to


@pytest.mark.parametrize('cast_it',[False,True])
def test_greatness_cold_actual_exact_cast_or_decline_then_scry(cards,tmp_path,cast_it):
    s=gameplay.setup(cards,'In Search of Greatness')
    put(s,'In Search of Greatness','battlefield')
    put(s,'Grizzly Bears','battlefield')
    altar=put(s,"Ashnod's Altar",'hand')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'greatness.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[altar.id] if cast_it else []})
    if cast_it:
        assert s.state.cards[altar.id].zone=='p1:battlefield'
        assert s.state.rules.decision is None
    else:
        assert s.state.cards[altar.id].zone=='p1:hand'
        d=s.state.rules.decision
        assert 'scry' in d.prompt.lower()
        s=fresh(s,cards,tmp_path/'scry.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[]})
        assert s.state.rules.decision is None


def test_squall_cold_actual_delve_paid_mill_then_foreign_graveyard_free_spell_with_exile_rider(cards,tmp_path):
    from tests.test_rules_bandmate_references import mana

    s=gameplay.setup(cards,'Sorcerous Squall')
    fuel=gameplay.squall_fuel(s)
    spell=put(s,'Divination','graveyard',pid='p2')
    source=put(s,'Sorcerous Squall','hand')
    mana(s,U=3)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'],contributions=[{'kind':'delve','card':c.id} for c in fuel])
    s=fresh(s,cards,tmp_path/'delved.json',s.state.rules.priority,{'type':'pass_priority'})
    assert all(s.state.cards[c.id].zone=='p1:exile' for c in fuel)
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    s=fresh(s,cards,tmp_path/'cast.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[spell.id]})
    assert s.state.cards[spell.id].zone=='p2:exile'


def test_talent_cold_public_reveal_first_and_second_spell_then_rest_graveyard(cards,tmp_path):
    from tests.test_rules_ordered_tutor_continuations import cast
    from tests.test_rules_refused_look import stack_library

    s=gameplay.setup(cards,'Talent of the Telepath','Murder','Earthquake')
    put(s,'Murder','graveyard')
    put(s,'Earthquake','graveyard')
    packet=stack_library(s,['Divination','Giant Growth','Grizzly Bears'],pid='p2')
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Talent of the Telepath',targets=['p2'])
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'first.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[packet[0]]})
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    assert s.state.cards[packet[0]].zone=='stack'
    s=fresh(s,cards,tmp_path/'second.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[packet[1]]})
    d=s.state.rules.decision
    if d is not None:
        s=fresh(s,cards,tmp_path/'target.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[bear.id]})
    assert all(s.state.cards[cid].zone=='p2:graveyard' for cid in packet)


def test_widow_cold_optional_counter_decline_then_normal_paid_foreign_spell(cards,tmp_path):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_refused_look import stack_library

    s=gameplay.setup(cards,'Black Widow, Super Spy')
    source=put(s,'Black Widow, Super Spy','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Divination','Grizzly Bears'],pid='p2')
    d=gameplay.combat_optional_offer(s,source)
    s=fresh(s,cards,tmp_path/'counter.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['decline']})
    assert s.state.rules.permissions
    to_phase(s,'main2',turn=4)
    mana(s,G=3)
    s=fresh(s,cards,tmp_path/'cast.json','p1',{'type':'cast_spell','card_id':packet[0]})
    assert s.state.cards[packet[0]].zone=='p2:graveyard'


def test_reno_cold_optional_sacrifice_then_normal_paid_exile_spell(cards,tmp_path):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_refused_look import stack_library

    s=gameplay.setup(cards,'Reno and Rude')
    source=put(s,'Reno and Rude','battlefield')
    altar=put(s,"Ashnod's Altar",'battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Divination','Grizzly Bears'],pid='p2')
    d=gameplay.combat_optional_offer(s,source)
    if 'pay' in [o.id for o in d.options]:
        s=fresh(s,cards,tmp_path/'accept.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['pay']})
        d=s.state.rules.decision
    if d is not None:
        s=fresh(s,cards,tmp_path/'sac.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[altar.id]})
    assert s.state.cards[altar.id].zone=='p1:graveyard'
    to_phase(s,'main2',turn=4)
    mana(s,G=3)
    s=fresh(s,cards,tmp_path/'cast.json','p1',{'type':'cast_spell','card_id':packet[0]})
    assert s.state.cards[packet[0]].zone=='p2:graveyard'


def test_diluvian_cold_all_opponent_targets_announced_before_ordered_casts_with_exile_riders(cards,tmp_path):
    from tests.test_rules_ordered_tutor_continuations import cast

    s=gameplay.setup(cards,'Diluvian Primordial')
    first=put(s,'Divination','graveyard',pid='p2')
    second=put(s,'Giant Growth','graveyard',pid='p3')
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Diluvian Primordial')
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'first-target.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[first.id]})
    d=s.state.rules.decision
    assert d.resume['step']=='trigger_group'
    assert s.state.cards[first.id].zone=='p2:graveyard'
    s=fresh(s,cards,tmp_path/'second-target.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[second.id]})
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    s=fresh(s,cards,tmp_path/'first-cast.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[first.id]})
    assert s.state.cards[first.id].zone=='stack'
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    s=fresh(s,cards,tmp_path/'second-cast.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[second.id]})
    d=s.state.rules.decision
    if d is not None:
        s=fresh(s,cards,tmp_path/'spell-target.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[bear.id]})
    assert s.state.cards[first.id].zone=='p2:exile'
    assert s.state.cards[second.id].zone=='p3:exile'


def test_jetsam_cold_all_mills_then_each_current_graveyard_cast_and_exact_rider(cards,tmp_path):
    from tests.test_rules_bandmate_references import mana

    s=gameplay.setup(cards,'Flotsam // Jetsam')
    first=put(s,"Ashnod's Altar",'graveyard',pid='p2')
    second=put(s,'Divination','graveyard',pid='p3')
    source=put(s,'Flotsam // Jetsam','hand')
    mana(s,U=2,C=4)
    act(s,'p1',type='cast_spell',card_id=source.id,face=1)
    settle(s)
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'first.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[first.id]})
    assert s.state.cards[first.id].zone=='stack'
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    s=fresh(s,cards,tmp_path/'second.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[second.id]})
    assert s.state.cards[first.id].zone=='p1:battlefield'
    assert s.state.cards[second.id].zone=='p3:exile'
    assert s.state.cards[source.id].zone=='p1:graveyard'
