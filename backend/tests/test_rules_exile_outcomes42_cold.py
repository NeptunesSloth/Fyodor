"""Production-only fresh-process payment snapshots and exact granted ability continuations."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests import test_rules_exile_outcomes42_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle

cards=gameplay.cards


def fresh(s,cards,path,actor,payload):
    from app.game.session import GameSession
    from app.game.state import GameState

    path.write_text(s.state.model_dump_json())
    code='''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(path.parent/'cold-images'))
s=GameSession(GameState.model_validate_json(path.read_text()),cards=repo)
s.perform(sys.argv[3],json.loads(sys.argv[4]))
for _ in range(60):
 d=s.state.rules.decision
 if d is not None:
  if d.kind=='order' and d.resume.get('step')!='order_library':
   s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[o.id for o in d.options]})
  else:
   break
 elif s.state.zones.get('stack'):
  s.perform(s.state.rules.priority,{'type':'pass_priority'})
 else:
  break
path.write_text(s.state.model_dump_json())
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),actor,json.dumps(payload)],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    return GameSession(GameState.model_validate_json(path.read_text()),cards=cards)



def test_paid_snapshot_survives_cold_mana_sacrifice_and_second_cold_payment(cards,tmp_path):
    s=gameplay.setup(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    altar=put(s,"Ashnod's Altar",'battlefield')
    growth=put(s,'Giant Growth','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bear.id])
    settle(s)
    source=put(s,"Lifestream's Blessing",'hand')
    act(s,'p1',type='set_prefs',payment='self')
    mana(s,C=2,G=2)
    act(s,'p1',type='cast_spell',card_id=source.id)
    assert s.state.rules.decision.resume['cast_greatest_power']==5
    before=len(s.state.zones.get('p1:hand',[]))
    s=fresh(s,cards,tmp_path/'paid.json','p1',{'type':'activate_ability','card_id':altar.id,'ability':0,
        'cost_choices':[{'component':0,'cards':[bear.id]}]})
    if s.state.rules.decision is not None:
        d=s.state.rules.decision
        s=fresh(s,cards,tmp_path/'paid2.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['pay']})
    assert s.state.cards[bear.id].zone=='p1:graveyard'
    assert len(s.state.zones.get('p1:hand',[]))==before-1+5
    assert s.state.cards[source.id].zone=='p1:graveyard'


def test_rivaz_cold_trigger_transfers_only_actual_granted_death_ability(cards,tmp_path):
    s=gameplay.setup(cards)
    put(s,'Rivaz of the Claw','battlefield')
    dragon=put(s,'Dragon Whelp','graveyard')
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    s=fresh(s,cards,tmp_path/'rivaz.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.cards[dragon.id].zone=='p1:battlefield'
    assert sum(a.text=='When this creature dies, exile it.' for a in gameplay.ch(s,s.state.cards[dragon.id]).abilities)==1
    murder=put(s,'Murder','hand')
    mana(s,C=1,B=2)
    act(s,'p1',type='cast_spell',card_id=murder.id,targets=[dragon.id])
    s=fresh(s,cards,tmp_path/'death.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.cards[dragon.id].zone=='p1:exile'


def test_immediate_free_snapshot_survives_cold_tax_payment_and_mana_sacrifice(cards,tmp_path):
    from tests.test_rules_controller_tutors import answer
    from tests.test_rules_ordered_tutor_continuations import cast
    s=gameplay.setup(cards,'Allure of the Unknown','Thalia, Guardian of Thraben')
    put(s,'Thalia, Guardian of Thraben','battlefield')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    altar=put(s,"Ashnod's Altar",'battlefield','p2')
    act(s,'p2',type='set_prefs',hold_priority=True,payment='self')
    source=put(s,"Lifestream's Blessing",'library')
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'library'},position='top')
    cast(s,'Allure of the Unknown')
    answer(s,['p2'])
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==source.id)])
    d=s.state.rules.decision
    act(s,'p2',type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.card_id==source.id)])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    assert s.state.rules.decision.resume['cast_greatest_power']==2
    s=fresh(s,cards,tmp_path/'free.json','p2',{'type':'activate_ability','card_id':altar.id,'ability':0,
        'cost_choices':[{'component':0,'cards':[bear.id]}]})
    if s.state.rules.decision is not None:
        d=s.state.rules.decision
        s=fresh(s,cards,tmp_path/'free2.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['pay']})
    assert s.state.players['p2'].life==44
    assert s.state.cards[bear.id].zone=='p2:graveyard'


def test_dance_cold_cursor_then_cold_free_cast_uses_exact_exiled_packet(cards,tmp_path):
    from tests.test_rules_refused_look import stack_library
    s=gameplay.setup(cards,'Dance with Calamity','Memnite')
    source=put(s,'Dance with Calamity','hand')
    ids=stack_library(s,['Memnite'])
    other=[cid for cid in s.state.zones['p1:library'] if cid not in ids]
    act(s,'p1',type='move',card_ids=other,to={'player':'p1','zone':'graveyard'})
    mana(s,C=7,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'dance.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['yes']})
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    option=next(o for o in d.options if o.card_id is not None)
    cid=option.card_id
    assert s.state.cards[cid].name=='Memnite' and s.state.cards[cid].zone=='p1:exile'
    s=fresh(s,cards,tmp_path/'dance-cast.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[option.id]})
    assert s.state.cards[cid].zone=='p1:battlefield'
    assert s.state.rules.free_cast_then is None


def test_theorist_cold_discard_choice_grants_exact_normal_paid_cast(cards,tmp_path):
    from tests.test_rules_controller_tutors import answer
    from tests.test_rules_wave30m_durations import to_phase
    s=gameplay.setup(cards,'Conspiracy Theorist','Merfolk Looter')
    put(s,'Conspiracy Theorist','battlefield')
    looter=put(s,'Merfolk Looter','battlefield')
    dragon=put(s,'Dragon Whelp','hand')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    d=s.state.rules.decision
    assert d.resume['step']=='exile_outcomes42_discard'
    s=fresh(s,cards,tmp_path/'discard.json',d.player,{'type':'choose','decision_id':d.id,
        'option_ids':[next(o.id for o in d.options if o.card_id==dragon.id)]})
    assert s.state.cards[dragon.id].zone=='p1:exile'
    mana(s,C=2,R=2)
    s=fresh(s,cards,tmp_path/'cast.json','p1',{'type':'cast_spell','card_id':dragon.id})
    assert s.state.cards[dragon.id].zone=='p1:battlefield'


def test_monk_cold_exile_trigger_visible_self_ability_survives_class_departure_and_casts(cards,tmp_path):
    from tests.test_rules_refused_look import stack_library
    from tests.test_rules_wave30m_durations import to_phase
    s=gameplay.setup(cards,'Monk Class','Disenchant')
    source=gameplay.monk_level_three(s)
    top=stack_library(s,['Dragon Whelp'])[0]
    to_phase(s,'upkeep',turn=4)
    s=fresh(s,cards,tmp_path/'monk-exile.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.cards[top].zone=='p1:exile'
    assert any(a.text==gameplay.leaf.MONK_ABILITY for a in gameplay.ch(s,s.state.cards[top]).abilities)
    assert not any(p.card==top for p in s.state.rules.permissions)
    to_phase(s,'main1',turn=4)
    disenchant=put(s,'Disenchant','hand')
    mana(s,C=1,W=1)
    s=fresh(s,cards,tmp_path/'class-gone.json','p1',{'type':'cast_spell','card_id':disenchant.id,'targets':[source.id]})
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert any(a['text']==gameplay.leaf.MONK_ABILITY for a in s.view('p1')['rules']['stats'][top]['abilities'])
    mana(s,C=2,R=2)
    s=fresh(s,cards,tmp_path/'monk-cast.json','p1',{'type':'cast_spell','card_id':top})
    assert s.state.cards[top].zone=='p1:battlefield'
    assert not any(a.text==gameplay.leaf.MONK_ABILITY for a in gameplay.ch(s,s.state.cards[top]).abilities)


def test_intellect_cold_opponent_hand_choices_do_not_move_any_card_before_all_choices(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_library_look import settle
    s=gameplay.setup(cards,'Intellect Devourer','Forest')
    source=put(s,'Intellect Devourer','hand')
    dragon=put(s,'Dragon Whelp','hand','p2')
    forest=put(s,'Forest','hand','p3')
    mana(s,C=3,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    assert d.player=='p2'
    s=fresh(s,cards,tmp_path/'hand2.json','p2',{'type':'choose','decision_id':d.id,
        'option_ids':[next(o.id for o in d.options if o.card_id==dragon.id)]})
    assert s.state.cards[dragon.id].zone=='p2:hand'
    d=s.state.rules.decision
    assert d.player=='p3'
    s=fresh(s,cards,tmp_path/'hand3.json','p3',{'type':'choose','decision_id':d.id,
        'option_ids':[next(o.id for o in d.options if o.card_id==forest.id)]})
    assert all(s.state.cards[cid].zone.endswith(':exile') for cid in [dragon.id,forest.id])
    murder=put(s,'Murder','hand')
    mana(s,C=1,B=2)
    s=fresh(s,cards,tmp_path/'return.json','p1',{'type':'cast_spell','card_id':murder.id,'targets':[source.id]})
    assert s.state.cards[dragon.id].zone=='p2:hand' and s.state.cards[forest.id].zone=='p3:hand'





def test_kingpin_cold_actual_life_loss_trigger_and_permission_land_play(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_refused_look import stack_library
    from tests.test_rules_wave30m_durations import to_phase
    s=gameplay.setup(cards,'Ob Nixilis, Captive Kingpin','Spear Spewer','Forest')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    spear=put(s,'Spear Spewer','battlefield')
    to_phase(s,'main1',turn=4)
    top=stack_library(s,['Forest'])[0]
    act(s,'p1',type='activate_ability',card_id=spear.id,ability=next(a.index for a in gameplay.ch(s,spear).abilities if a.text.startswith('{T}')))
    s=fresh(s,cards,tmp_path/'kingpin.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.cards[kingpin.id].counters.get('+1/+1')==1
    assert s.state.cards[top].zone=='p1:exile'
    assert {'flying','trample'}<=gameplay.ch(s,s.state.cards[kingpin.id]).keywords
    s=fresh(s,cards,tmp_path/'kingpin-land.json','p1',{'type':'play_land','card_id':top})
    assert s.state.cards[top].zone=='p1:battlefield'


def test_kingpin_cold_original_simultaneous_effect_loss_vector_is_one_trigger(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_wave30m_durations import to_phase
    s=gameplay.setup(cards,'Ob Nixilis, Captive Kingpin','Pulse Tracker')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    tracker=put(s,'Pulse Tracker','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':tracker.id,'target':'p2'}])
    s=fresh(s,cards,tmp_path/'vector.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.players['p2'].life==39 and s.state.players['p3'].life==39
    assert s.state.cards[kingpin.id].counters.get('+1/+1')==1


def test_gale_cold_announced_target_then_paid_cast_preserves_frozen_opposite_type(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    s=gameplay.setup(cards,'Gale, Waterdeep Prodigy','Divination','Lightning Bolt')
    put(s,'Gale, Waterdeep Prodigy','battlefield')
    sorcery=put(s,'Divination','graveyard')
    instant=put(s,'Lightning Bolt','graveyard')
    bear=put(s,'Grizzly Bears','battlefield')
    growth=put(s,'Giant Growth','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bear.id])
    d=s.state.rules.decision
    assert instant.id not in {o.card_id for o in d.options}
    s=fresh(s,cards,tmp_path/'gale-target.json','p1',{'type':'choose','decision_id':d.id,
        'option_ids':[next(o.id for o in d.options if o.card_id==sorcery.id)]})
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    mana(s,C=2,U=1)
    s=fresh(s,cards,tmp_path/'gale-cast.json','p1',{'type':'choose','decision_id':d.id,
        'option_ids':[next(o.id for o in d.options if o.card_id==sorcery.id)]})
    assert s.state.cards[sorcery.id].zone=='p1:exile'
    assert s.state.cards[instant.id].zone=='p1:graveyard'


def test_triskaidekaphobia_cold_gain_mode_and_replacement_choice_preserve_original_operation(cards,tmp_path):
    from tests.test_rules_designations import put
    from tests.test_rules_library_look import settle
    from tests.test_rules_wave30m_durations import to_phase
    s=gameplay.setup(cards,'Triskaidekaphobia','Tainted Remedy','Boon Reflection','Ob Nixilis, Captive Kingpin')
    put(s,'Triskaidekaphobia','battlefield')
    put(s,'Tainted Remedy','battlefield')
    put(s,'Boon Reflection','battlefield','p2')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'trisk-mode.json',d.player,{'type':'choose','decision_id':d.id,
        'option_ids':[next(o.id for o in d.options if 'gains 1 life' in o.label.lower())]})
    d=s.state.rules.decision
    assert d.resume['site']=='life'
    operation=d.resume['request']['operation']
    assert operation==s.state.rules.next_life_operation>0
    s=fresh(s,cards,tmp_path/'trisk-replacement.json',d.player,{'type':'choose','decision_id':d.id,
        'option_ids':[next(o.id for o in d.options if 'Tainted Remedy' in o.label)]})
    assert s.state.players['p1'].life==41 and s.state.players['p2'].life==39 and s.state.players['p3'].life==39
    assert s.state.cards[kingpin.id].counters.get('+1/+1')==1


def test_wand_cold_exact_packet_sequential_free_casts_survive_source_departure(cards,tmp_path,monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    from tests.test_rules_library_look import settle
    from tests.test_rules_random_consequences import faces
    from tests.test_rules_refused_look import stack_library
    s=gameplay.setup(cards,'Wand of Wonder','Divination','Disenchant')
    wand=put(s,'Wand of Wonder','battlefield')
    stack_library(s,['Divination'],pid='p2')
    stack_library(s,['Divination'],pid='p3')
    faces(monkeypatch,[19])
    mana(s,C=4)
    act(s,'p1',type='activate_ability',card_id=wand.id,ability=0)
    disenchant=put(s,'Disenchant','hand')
    mana(s,C=1,W=1)
    act(s,'p1',type='cast_spell',card_id=disenchant.id,targets=[wand.id])
    settle(s)
    assert s.state.cards[wand.id].zone=='p1:graveyard'
    d=s.state.rules.decision
    first=next(o for o in d.options if o.card_id is not None)
    s=fresh(s,cards,tmp_path/'wand-first.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[first.id]})
    assert s.state.cards[first.card_id].zone=='stack'
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    second=next(o for o in d.options if o.card_id is not None)
    before=len(s.state.zones.get('p1:hand',[]))
    s=fresh(s,cards,tmp_path/'wand-second.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[second.id]})
    assert s.state.cards[first.card_id].zone=='p2:graveyard' or s.state.cards[first.card_id].zone=='p3:graveyard'
    assert s.state.cards[second.card_id].zone=='p2:graveyard' or s.state.cards[second.card_id].zone=='p3:graveyard'
    assert len(s.state.zones.get('p1:hand',[]))==before+4
    assert s.state.rules.free_cast_then is None


def test_tinybones_cold_each_opponent_discard_then_stash_land_and_wrong_color_paid_spell(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    from tests.test_rules_library_look import settle
    from tests.test_rules_wave30m_durations import to_phase
    s=gameplay.setup(cards,'Tinybones, Bauble Burglar','Forest')
    source=put(s,'Tinybones, Bauble Burglar','battlefield')
    dragon=put(s,'Dragon Whelp','hand','p2')
    forest=put(s,'Forest','hand','p3')
    to_phase(s,'main1',turn=4)
    mana(s,C=3,B=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=next(a.index for a in gameplay.ch(s,source).abilities if a.text.startswith('{3}')))
    settle(s)
    for cid in [dragon.id,forest.id]:
        d=s.state.rules.decision
        s=fresh(s,cards,tmp_path/(cid+'.json'),d.player,{'type':'choose','decision_id':d.id,
            'option_ids':[next(o.id for o in d.options if o.card_id==cid)]})
    assert all(s.state.cards[cid].counters.get('stash')==1 for cid in [dragon.id,forest.id])
    s=fresh(s,cards,tmp_path/'stash-land.json','p1',{'type':'play_land','card_id':forest.id})
    mana(s,C=4)
    s=fresh(s,cards,tmp_path/'stash-spell.json','p1',{'type':'cast_spell','card_id':dragon.id})
    assert s.state.cards[forest.id].zone=='p1:battlefield' and s.state.cards[dragon.id].zone=='p1:battlefield'


def test_grolnok_cold_native_frog_attack_mill_and_exact_croak_land_spell_permissions(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_refused_look import stack_library
    from tests.test_rules_wave30m_durations import to_phase
    s=gameplay.setup(cards,'Grolnok, the Omnivore','Forest','Memnite')
    source=put(s,'Grolnok, the Omnivore','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    top=stack_library(s,['Forest','Memnite','Murder'])
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    s=fresh(s,cards,tmp_path/'croak.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.cards[top[0]].counters.get('croak')==1 and s.state.cards[top[1]].counters.get('croak')==1
    assert s.state.cards[top[2]].zone=='p1:graveyard'
    to_phase(s,'main2',turn=4)
    s=fresh(s,cards,tmp_path/'croak-land.json','p1',{'type':'play_land','card_id':top[0]})
    s=fresh(s,cards,tmp_path/'croak-spell.json','p1',{'type':'cast_spell','card_id':top[1]})
    assert all(s.state.cards[cid].zone=='p1:battlefield' for cid in top[:2])


def test_narfi_cold_each_graveyard_choice_then_original_link_paid_spell(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    from tests.test_rules_library_look import settle
    s=gameplay.setup(cards,"King Narfi's Betrayal")
    dragon=put(s,'Dragon Whelp','graveyard','p2')
    source=put(s,"King Narfi's Betrayal",'hand')
    mana(s,C=1,U=1,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    for player in ('p1','p2','p3'):
        d=s.state.rules.decision
        chosen=[next(o.id for o in d.options if o.card_id==dragon.id)] if player=='p2' else []
        s=fresh(s,cards,tmp_path/'narfi.json','p1',{'type':'choose','decision_id':d.id,'option_ids':chosen})
    assert s.state.cards[dragon.id].zone=='p2:exile'
    gameplay.to_phase(s,'main1',turn=4)
    settle(s)
    mana(s,C=2,R=2)
    s=fresh(s,cards,tmp_path/'narfi.json','p1',{'type':'cast_spell','card_id':dragon.id})
    assert s.state.cards[dragon.id].zone=='p1:battlefield'


def test_lobelia_cold_private_exile_packet_then_sourcegone_one_land_permission(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    from tests.test_rules_library_look import settle
    from tests.test_rules_refused_look import stack_library
    s=gameplay.setup(cards,'Lobelia, Defender of Bag End','Forest','Memnite')
    gameplay.to_phase(s,'main1',turn=4)
    stack_library(s,['Forest'],pid='p2')
    stack_library(s,['Dragon Whelp'],pid='p3')
    source=put(s,'Lobelia, Defender of Bag End','hand')
    mana(s,C=2,B=1)
    s=fresh(s,cards,tmp_path/'lobelia.json','p1',{'type':'cast_spell','card_id':source.id})
    forest=next(c.id for c in s.state.cards.values() if c.owner=='p2' and c.name=='Forest' and c.zone=='p2:exile')
    gameplay.to_phase(s,'main1',turn=7)
    put(s,'Memnite','battlefield')
    ability=next(a.index for a in gameplay.ch(s,s.state.cards[source.id]).abilities if a.text.startswith('{T}'))
    s=fresh(s,cards,tmp_path/'lobelia.json','p1',{'type':'activate_ability','card_id':source.id,'ability':ability,'modes':[0]})
    murder=put(s,'Murder','hand')
    mana(s,C=1,B=2)
    act(s,'p1',type='cast_spell',card_id=murder.id,targets=[source.id])
    settle(s)
    s=fresh(s,cards,tmp_path/'lobelia.json','p1',{'type':'play_land','card_id':forest})
    assert s.state.cards[forest].zone=='p1:battlefield'
    assert s.state.cards[source.id].zone=='p1:graveyard'


def test_ruinous_cold_manual_payment_freezes_actual_x_owner_receipt_after_commit(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    s=gameplay.setup(cards,'The Ruinous Powers','Earthquake')
    source,cid=gameplay.ruinous_ready(s,'Earthquake')
    owner=s.state.cards[cid].owner
    act(s,'p1',type='set_prefs',payment='self')
    act(s,'p1',type='cast_spell',card_id=cid,x_value=2)
    d=s.state.rules.decision
    assert d.resume['step']=='pay_mana'
    assert not any(e.kind=='trigger' and e.source_card==source.id for e in s.state.rules.stack.values())
    mana(s,W=3)
    s=fresh(s,cards,tmp_path/'ruinous.json','p1',{'type':'choose','decision_id':d.id,'option_ids':['pay']})
    assert s.state.players[owner].life==35
    assert s.state.players['p1'].life==38
    assert s.state.cards[cid].zone==owner+':graveyard'


def test_share_cold_static_foreign_land_authority_shared_once_receipt_and_refill(cards,tmp_path):
    import pytest

    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    from tests.test_rules_refused_look import stack_library
    s=gameplay.setup(cards,'Share the Spoils','Forest','Memnite')
    forest=stack_library(s,['Forest'],pid='p2')[0]
    dragon=stack_library(s,['Dragon Whelp'],pid='p3')[0]
    source=put(s,'Share the Spoils','hand')
    mana(s,C=1,R=1)
    s=fresh(s,cards,tmp_path/'share.json','p1',{'type':'cast_spell','card_id':source.id})
    refill=stack_library(s,['Memnite'])[0]
    s=fresh(s,cards,tmp_path/'share.json','p1',{'type':'play_land','card_id':forest})
    assert s.state.cards[forest].zone=='p1:battlefield'
    assert s.state.cards[refill].zone=='p1:exile'
    mana(s,W=4)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragon)


def test_mara_cold_apnap_choice_then_immediate_cast_then_second_choice_damage(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    from tests.test_rules_library_look import settle
    from tests.test_rules_refused_look import stack_library
    s=gameplay.setup(cards,'Ensnared by the Mara','Forest','Memnite')
    first=stack_library(s,['Forest','Dragon Whelp'],pid='p2')
    second=stack_library(s,['Dragon Whelp','Memnite','Forest','Giant Growth'],pid='p3')
    source=put(s,'Ensnared by the Mara','hand')
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'mara.json','p2',{'type':'choose','decision_id':d.id,'option_ids':['cast']})
    d=s.state.rules.decision
    option=next(o.id for o in d.options if o.card_id==first[1])
    s=fresh(s,cards,tmp_path/'mara.json','p1',{'type':'choose','decision_id':d.id,'option_ids':[option]})
    d=s.state.rules.decision
    assert d.player=='p3' and s.state.cards[first[1]].zone=='stack'
    assert all(s.state.cards[cid].zone=='p3:library' for cid in second)
    s=fresh(s,cards,tmp_path/'mara.json','p3',{'type':'choose','decision_id':d.id,'option_ids':['damage']})
    assert s.state.players['p3'].life==35
    assert s.state.cards[first[1]].zone=='p1:battlefield'
    assert s.state.cards[source.id].zone=='p1:graveyard'


def test_quintorius_cold_sourcegone_free_permission_then_616_bottom_choice(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    from tests.test_rules_library_look import settle
    s=gameplay.setup(cards,'Quintorius, Loremaster','Rest in Peace')
    source,spell=gameplay.quintorius_ready(s)
    bear=put(s,'Grizzly Bears','battlefield')
    gameplay.quintorius_activate(s,source,spell)
    removal=put(s,'Murder','hand')
    mana(s,C=1,B=2)
    act(s,'p1',type='cast_spell',card_id=removal.id,targets=[source.id])
    settle(s)
    put(s,'Rest in Peace','battlefield')
    s=fresh(s,cards,tmp_path/'quintorius.json','p1',{'type':'cast_spell','card_id':spell.id,'free':True,'targets':[bear.id]})
    d=s.state.rules.decision
    assert d.resume['step']=='zone_replace_order'
    option=next(o.id for o in d.options if 'bottom' in o.label.lower())
    s=fresh(s,cards,tmp_path/'quintorius.json','p1',{'type':'choose','decision_id':d.id,'option_ids':[option]})
    assert s.state.cards[spell.id].zone=='p1:library'
    assert s.state.zones['p1:library'][-1]==spell.id
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert not s.state.rules.bottom_if_graveyard


def test_season_reviewed_zero_mode_and_payment_receipt_survive_two_true_cold_resumes(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    s=gameplay.setup(cards,'Season of the Bold')
    source=put(s,'Season of the Bold','hand')
    act(s,'p1',type='set_prefs',payment='self')
    act(s,'p1',type='cast_spell',card_id=source.id)
    d=s.state.rules.decision
    assert d.resume['step']=='cast_modes' and d.min_choices==0
    s=fresh(s,cards,tmp_path/'season-zero.json','p1',{'type':'choose','decision_id':d.id,'option_ids':[]})
    d=s.state.rules.decision
    assert d.resume['step']=='pay_mana' and d.resume['zero_modes_object']==s.state.rules.object_id(source.id)
    mana(s,C=3,R=2)
    s=fresh(s,cards,tmp_path/'season-zero.json','p1',{'type':'choose','decision_id':d.id,'option_ids':['pay']})
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert not s.state.rules.delayed and not s.state.rules.permissions


def test_season_reviewed_pre_mode_authority_then_zero_additional_cost_true_cold(cards,tmp_path):
    from app.game.rules_state import Permission
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    s=gameplay.setup(cards,'Season of the Bold','Memnite')
    source=put(s,'Season of the Bold','exile')
    first=put(s,'Dragon Whelp','hand')
    second=put(s,'Memnite','hand')
    for key,extra in [('plain',''),('discard','discard a card')]:
        s.state.rules.permissions.append(Permission(id=key,player='p1',card=source.id,object_id=s.state.rules.object_id(source.id),zone='any',
            cast=True,free=True,once=True,extra=extra,until='end_of_turn',turn=1,label=key))
    act(s,'p1',type='cast_spell',card_id=source.id,free=True)
    d=s.state.rules.decision
    option=next(o.id for o in d.options if 'discard' in o.label)
    s=fresh(s,cards,tmp_path/'season-cost.json','p1',{'type':'choose','decision_id':d.id,'option_ids':[option]})
    d=s.state.rules.decision
    assert d.resume['step']=='cast_modes' and d.min_choices==0
    s=fresh(s,cards,tmp_path/'season-cost.json','p1',{'type':'choose','decision_id':d.id,'option_ids':[]})
    d=s.state.rules.decision
    assert d.resume['step']=='ability_cost' and 'zero_modes_object' in d.resume
    option=next(o.id for o in d.options if o.card_id==first.id)
    s=fresh(s,cards,tmp_path/'season-cost.json','p1',{'type':'choose','decision_id':d.id,'option_ids':[option]})
    assert s.state.cards[first.id].zone=='p1:graveyard' and s.state.cards[second.id].zone=='p1:hand'
    assert s.state.cards[source.id].zone=='p1:graveyard'

def test_season_cold_exact_packet_cast_future_target_and_original_source_damage(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    from tests.test_rules_library_look import settle
    from tests.test_rules_refused_look import stack_library
    s=gameplay.setup(cards,'Season of the Bold','Memnite','Forest')
    packet=stack_library(s,['Memnite','Forest'])
    target=put(s,'Grizzly Bears','battlefield','p2')
    source=put(s,'Season of the Bold','hand')
    mana(s,C=3,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id,modes=[1,2])
    settle(s)
    s=fresh(s,cards,tmp_path/'season.json','p1',{'type':'cast_spell','card_id':packet[0]})
    d=s.state.rules.decision
    assert d.min_choices==0 and d.max_choices==1
    option=next(o.id for o in d.options if o.card_id==target.id)
    s=fresh(s,cards,tmp_path/'season.json','p1',{'type':'choose','decision_id':d.id,'option_ids':[option]})
    assert s.state.cards[target.id].zone=='p2:graveyard'
    assert s.state.cards[packet[0]].zone=='p1:battlefield'
    gameplay.to_phase(s,'main1',turn=4)
    s=fresh(s,cards,tmp_path/'season.json','p1',{'type':'play_land','card_id':packet[1]})
    assert s.state.cards[packet[1]].zone=='p1:battlefield'
