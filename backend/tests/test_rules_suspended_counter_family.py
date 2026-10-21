"""Canonical suspended objects share exact counter operations and native suspend triggers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Deep-Sea Kraken','Pardic Dragon','Greater Gargadon','Amy Pond','Clockspinning',"Jhoira's Timebug",'Rift Elemental',"Venser's Diffusion",'Dust of Moments','Nihilith']
EXTRA=['Suspend','Reverberate','Doubling Season','Hardened Scales','Counterspell','Disenchant','Shock','Solemnity','Rift Bolt','Doom Blade','Rest in Peace','Lightning Greaves','Hymn to Tourach','Raise the Alarm','Opt','Sol Ring','Grizzly Bears','Llanowar Elves','Forest']

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/suspended_counter_family_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='scf',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    ns=[*NAMES,*EXTRA]
    return table(cards,ns,ns,ns)


def suspend(s,name,pid='p1'):
    source=put(s,name,'hand',pid)
    ch=chars(s,source)
    ab=next(a.index for a in ch.abilities if 'suspend' in a.keywords)
    n,cost=casting.suspend_info(ch,ab)
    from app.rules import mana as M
    parsed=M.parse_cost(cost)
    pool={'C':parsed.generic}
    for color in parsed.colored:
        pool[color]=pool.get(color,0)+1
    mana(s,pid=pid,**pool)
    wait_priority(s,pid)
    act(s,pid,type='activate_ability',card_id=source.id,ability=ab,sources=[])
    assert s.state.cards[source.id].zone==f'{pid}:exile'
    assert s.state.cards[source.id].counters.get('time')==n
    return source


def choose(s,value):
    d=s.state.rules.decision
    assert d and value in {o.id for o in d.options},(d,value)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
    settle(s)


def cast(s,name,target=None,pid='p1',**kwargs):
    source=put(s,name,'hand',pid)
    pay(s,pid,name)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=[target] if target else [],sources=[],**kwargs)
    settle(s)
    return source


@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_deep_sea_kraken_actual_suspend_opponent_cast_and_own_cast_boundary(cards):
    s=game(cards)
    source=suspend(s,'Deep-Sea Kraken')
    cast(s,'Opt')
    d=s.state.rules.decision
    if d:
        choose(s,d.options[0].id)
        if s.state.rules.decision:
            choose(s,s.state.rules.decision.options[0].id)
    assert s.state.cards[source.id].counters['time']==9
    cast(s,'Shock','p3',pid='p2')
    assert s.state.cards[source.id].counters['time']==8
    assert s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)

@pytest.mark.parametrize('accept',[False,True])
def test_pardic_dragon_opponent_controls_optional_time_counter(cards,accept):
    s=game(cards)
    source=suspend(s,'Pardic Dragon')
    cast(s,'Shock','p3',pid='p2')
    d=s.state.rules.decision
    assert d and d.player=='p2' and d.resume['step']=='suspended_counter_choice'
    roundtrip(s)
    choose(s,'add' if accept else 'decline')
    assert s.state.cards[source.id].counters['time']==2+int(accept)
    roundtrip(s)


def test_nihilith_actual_opponent_graveyard_entry_triggers_own_optional_removal(cards):
    s=game(cards)
    source=suspend(s,'Nihilith')
    victim=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'Doom Blade',victim.id)
    d=s.state.rules.decision
    assert d and d.player=='p1'
    choose(s,'yes')
    assert s.state.cards[source.id].counters['time']==6
    roundtrip(s)

@pytest.mark.parametrize('payment',['Sol Ring','Grizzly Bears','Forest'])
def test_greater_gargadon_actual_sacrifice_or_cost_works_from_exile(cards,payment):
    s=game(cards)
    source=suspend(s,'Greater Gargadon')
    victim=put(s,payment,'battlefield')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=next(a.index for a in chars(s,source).abilities if a.kind=='activated'),sources=[])
    settle(s)
    assert s.state.cards[victim.id].zone=='p1:graveyard'
    assert s.state.cards[source.id].counters['time']==9
    roundtrip(s)


def test_clockspinning_kind_then_add_and_remove_on_real_suspended_card(cards):
    s=game(cards)
    source=suspend(s,'Deep-Sea Kraken')
    cast(s,'Clockspinning',source.id)
    choose(s,'time')
    roundtrip(s)
    choose(s,'add')
    assert s.state.cards[source.id].counters['time']==10
    roundtrip(s)


def test_timebug_actual_tap_ability_optional_choice_on_suspended_card(cards):
    s=game(cards)
    bug=put(s,"Jhoira's Timebug",'battlefield')
    source=suspend(s,'Deep-Sea Kraken')
    to_phase(s,'main1',turn=4)
    before=s.state.cards[source.id].counters['time']
    act(s,'p1',type='activate_ability',card_id=bug.id,ability=0,targets=[source.id],sources=[])
    settle(s)
    choose(s,'remove')
    assert s.state.cards[bug.id].tapped
    assert s.state.cards[source.id].counters['time']==before-1
    roundtrip(s)


def test_rift_elemental_actual_counter_cost_can_use_owned_suspended_card(cards):
    s=game(cards)
    elemental=put(s,'Rift Elemental','battlefield')
    source=suspend(s,'Deep-Sea Kraken')
    mana(s,C=1,R=1)
    act(s,'p1',type='activate_ability',card_id=elemental.id,ability=0,sources=[])
    d=s.state.rules.decision
    if d:
        choose(s,source.id)
    settle(s)
    assert s.state.cards[source.id].counters['time']==8
    assert chars(s,s.state.cards[elemental.id]).pt==(3,1)
    roundtrip(s)


def test_venser_diffusion_returns_suspended_card_to_owner_and_drops_grant(cards):
    s=game(cards)
    source=suspend(s,'Deep-Sea Kraken')
    cast(s,"Venser's Diffusion",source.id)
    assert s.state.cards[source.id].zone=='p1:hand'
    assert source.id not in s.state.rules.suspended
    assert not s.state.cards[source.id].counters
    roundtrip(s)

@pytest.mark.parametrize('mode',[0,1])
def test_dust_of_moments_actual_modes_change_permanents_and_suspended_cards(cards,mode):
    s=game(cards)
    source=suspend(s,'Deep-Sea Kraken')
    ring=put(s,'Sol Ring','battlefield')
    act(s,'p1',type='set_counter',card_id=ring.id,kind='time',value=3)
    cast(s,'Dust of Moments',modes=[mode])
    assert s.state.cards[source.id].counters['time']==(7 if mode==0 else 11)
    assert s.state.cards[ring.id].counters['time']==(1 if mode==0 else 5)
    roundtrip(s)


def test_amy_actual_unblocked_combat_damage_chooses_owned_suspended_card(cards):
    s=game(cards)
    amy=put(s,'Amy Pond','battlefield')
    source=suspend(s,'Deep-Sea Kraken')
    to_phase(s,'declare_attackers',turn=4)
    before=s.state.cards[source.id].counters['time']
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':amy.id,'target':'p2'}])
    to_phase(s,'combat_damage')
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='suspended_counter_choice'
    roundtrip(s)
    choose(s,source.id)
    assert s.state.cards[source.id].counters['time']==before-2
    assert s.state.players['p2'].life==38
    roundtrip(s)


def grant_suspend_to_bear(s):
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Suspend',bear.id)
    assert bear.id in s.state.rules.suspended and s.state.cards[bear.id].counters['time']==2
    return bear


def clock(s,target,mode='remove',kind='time',buyback=False):
    source=put(s,'Clockspinning','hand')
    mana(s,U=1,**({'C':3} if buyback else {}))
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[target.id],buyback=buyback,sources=[])
    settle(s)
    choose(s,kind)
    choose(s,mode)
    return source


def test_printed_suspend_in_exile_without_registration_uses_native_last_counter_cast_haste(cards):
    from app.rules.plan import Plan
    from app.rules.suspend_grants import is_suspended
    s=game(cards)
    source=put(s,'Greater Gargadon','exile')
    act(s,'p1',type='set_counter',card_id=source.id,kind='time',value=1)
    assert source.id not in s.state.rules.suspended
    assert is_suspended(Plan.view(s.state,'p1',s.cards),s.state.cards[source.id])
    clock(s,source)
    d=s.state.rules.decision
    assert d and d.resume['step']=='suspend_cast'
    roundtrip(s)
    choose(s,'yes')
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert 'haste' in chars(s,s.state.cards[source.id]).keywords
    assert source.id not in s.state.rules.suspended
    roundtrip(s)


def test_granted_suspend_remains_at_zero_after_declining_but_zero_is_not_a_legal_target(cards):
    from app.rules.plan import Plan
    from app.rules.suspend_grants import has_suspend, is_suspended
    s=game(cards)
    bear=grant_suspend_to_bear(s)
    cast(s,'Dust of Moments',modes=[0])
    choose(s,'no')
    current=s.state.cards[bear.id]
    view=Plan.view(s.state,'p1',s.cards)
    assert has_suspend(view,current) and not is_suspended(view,current)
    assert bear.id in s.state.rules.suspended
    source=put(s,'Clockspinning','hand')
    mana(s,U=1)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,targets=[bear.id],sources=[])
    # A manual counter state edit is allowed; it is not a falsely legal Clock target at zero.
    act(s,'p1',type='set_counter',card_id=bear.id,kind='time',value=1)
    assert is_suspended(Plan.view(s.state,'p1',s.cards),s.state.cards[bear.id])
    clock(s,bear)
    choose(s,'yes')
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    assert 'haste' in chars(s,s.state.cards[bear.id]).keywords
    roundtrip(s)


def test_granted_suspend_does_not_survive_new_exile_incarnation(cards):
    from app.rules.plan import Plan
    from app.rules.suspend_grants import has_suspend
    s=game(cards)
    bear=grant_suspend_to_bear(s)
    old=s.state.rules.object_id(bear.id)
    cast(s,"Venser's Diffusion",bear.id)
    assert bear.id not in s.state.rules.suspended
    bear=put(s,'Grizzly Bears','exile')
    act(s,'p1',type='set_counter',card_id=bear.id,kind='time',value=1)
    assert s.state.rules.object_id(bear.id)!=old
    assert not has_suspend(Plan.view(s.state,'p1',s.cards),s.state.cards[bear.id])
    to_phase(s,'main1',turn=4)
    assert s.state.cards[bear.id].counters['time']==1
    assert s.state.rules.decision is None
    roundtrip(s)


def test_clock_permanent_doubling_replacements_apply_but_do_not_double_exile_counter(cards):
    s=game(cards)
    put(s,'Doubling Season','battlefield')
    ring=put(s,'Sol Ring','battlefield')
    act(s,'p1',type='set_counter',card_id=ring.id,kind='charge',value=1)
    clock_spell=clock(s,ring,'add','charge',True)
    assert s.state.cards[clock_spell.id].zone=='p1:hand'
    assert s.state.cards[ring.id].counters['charge']==3
    source=suspend(s,'Deep-Sea Kraken')
    clock(s,source,'add')
    assert s.state.cards[source.id].counters['time']==10
    roundtrip(s)


def test_gargadon_activation_is_from_exile_only_and_only_currently_suspended(cards):
    s=game(cards)
    source=put(s,'Greater Gargadon','battlefield')
    ring=put(s,'Sol Ring','battlefield')
    index=next(a.index for a in chars(s,source).abilities if a.kind=='activated')
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=index,sources=[])
    source=put(s,'Greater Gargadon','exile')
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=index,sources=[])
    assert s.state.cards[ring.id].zone=='p1:battlefield'
    roundtrip(s)

@pytest.mark.parametrize('stage',['kind','mode','replacement'])
def test_clock_choices_and_counter_replacement_order_resume_in_fresh_process(cards,tmp_path,stage):
    import subprocess
    import sys

    s=game(cards)
    target=put(s,'Grizzly Bears','battlefield')
    act(s,'p1',type='set_counter',card_id=target.id,kind='+1/+1',value=1)
    act(s,'p1',type='set_counter',card_id=target.id,kind='charge',value=1)
    put(s,'Doubling Season','battlefield')
    put(s,'Hardened Scales','battlefield')
    cast(s,'Clockspinning',target.id)
    if stage!='kind':
        choose(s,'+1/+1')
    if stage=='replacement':
        choose(s,'add')
    assert s.state.rules.decision
    saved=tmp_path/f'clock-{stage}.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,db,target=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
for _ in range(30):
 d=s.state.rules.decision
 if d:
  answer=d.resume.get('answer')
  pick='+1/+1' if answer=='kind' else 'add' if answer=='mode' else d.options[0].id
  s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[pick]})
 elif s.state.zones['stack']:
  s.perform(s.state.rules.priority,{'type':'pass_priority'})
 else:break
else:raise AssertionError('did not finish')
assert s.state.cards[target].counters['charge']==1
assert s.state.cards[target].counters['+1/+1'] in (4,5)
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),target.id],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_clock_last_counter_native_suspend_cast_resumes_cold_with_haste(cards,tmp_path):
    import subprocess
    import sys

    s=game(cards)
    source=suspend(s,'Greater Gargadon')
    act(s,'p1',type='set_counter',card_id=source.id,kind='time',value=1)
    clock(s,source)
    d=s.state.rules.decision
    assert d and d.resume['step']=='suspend_cast'
    saved=tmp_path/'gargadon-last.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle
from tests.test_rules_wave6c_tokens_pumps import chars
save,db,source=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['yes']})
settle(s)
assert s.state.cards[source].zone=='p1:battlefield'
assert 'haste' in chars(s,s.state.cards[source]).keywords
assert source not in s.state.rules.suspended
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('grant_path',['granted','permission'])
def test_zero_counter_suspend_capability_does_not_grant_haste_to_an_unrelated_free_cast(cards,grant_path):
    from app.rules import context, effects, granted_casts, permissions
    from app.rules.plan import Plan

    s=game(cards)
    bear=grant_suspend_to_bear(s)
    cast(s,'Dust of Moments',modes=[0])
    choose(s,'no')
    assert bear.id in s.state.rules.suspended
    plan=Plan(s.state.model_copy(deep=True),'p1',cards,None)
    # Low-level native grant contrast: this is not presented as another canonical
    # card's effect. The exact same exile object still HAS suspend at zero.
    ctx={'controller':'p1','source_card':None,'source_object':None,'stack_id':'test-generic-cast',
         'name':'Independent free-cast grant','effects':[],'next':0}
    if grant_path=='granted':
        assert not granted_casts.ask(plan,ctx,player='p1',cid=bear.id,head='Independent grant',no='Decline')
    else:
        context.bind_objects(plan,ctx,'independent_target',[bear.id])
        assert not permissions.free_cast(plan,ctx,{'do':'free_cast','zone':'that','who':'ref:independent_target','n':1})
    d=plan.rules.decision
    assert d is not None
    plan.rules.decision=None
    if grant_path=='granted':
        effects.resume_suspend_cast(plan,d,['yes'])
    else:
        permissions.resume_free_cast(plan,d,[bear.id])
    assert plan.state.cards[bear.id].zone=='stack'
    assert bear.id not in plan.rules.suspend_haste


def test_clock_target_ceases_to_be_suspended_before_resolution_and_is_illegal(cards):
    s=game(cards)
    source=suspend(s,'Deep-Sea Kraken')
    act(s,'p1',type='set_counter',card_id=source.id,kind='time',value=1)
    spell=put(s,'Clockspinning','hand')
    mana(s,U=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[source.id],sources=[])
    shock=put(s,'Shock','hand','p2')
    mana(s,pid='p2',R=1)
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=shock.id,targets=['p3'],sources=[])
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.resume['step']=='suspend_cast'
    choose(s,'no')
    assert s.state.rules.decision is None
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    assert s.state.cards[source.id].zone=='p1:exile' and not s.state.cards[source.id].counters
    roundtrip(s)


def test_nihilith_each_of_two_actual_simultaneous_discarded_cards_gives_a_trigger(cards):
    s=game(cards)
    source=suspend(s,'Nihilith')
    for cid in list(s.state.zones['p2:hand']):
        act(s,'p2',type='move',card_ids=[cid],to={'player':'p2','zone':'library'})
    a=put(s,'Grizzly Bears','hand','p2')
    b=put(s,'Llanowar Elves','hand','p2')
    cast(s,'Hymn to Tourach','p2')
    for _ in range(2):
        assert s.state.rules.decision and s.state.rules.decision.player=='p1'
        choose(s,'yes')
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].counters['time']==5
    assert s.state.cards[a.id].zone=='p2:graveyard' and s.state.cards[b.id].zone=='p2:graveyard'
    roundtrip(s)


def test_nihilith_does_not_trigger_for_a_token_entering_opponents_graveyard(cards):
    s=game(cards)
    cast(s,'Raise the Alarm',pid='p2')
    token=next(c for c in s.state.cards.values() if c.is_token and c.zone=='p2:battlefield')
    source=suspend(s,'Nihilith')
    cast(s,'Doom Blade',token.id)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].counters['time']==7
    roundtrip(s)


def test_nihilith_does_not_count_a_death_replaced_with_exile(cards):
    s=game(cards)
    source=suspend(s,'Nihilith')
    put(s,'Rest in Peace','battlefield')
    victim=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'Doom Blade',victim.id)
    assert s.state.cards[victim.id].zone=='p2:exile'
    assert s.state.rules.decision is None and s.state.cards[source.id].counters['time']==7
    roundtrip(s)


def test_pending_deep_trigger_does_not_remove_from_new_exile_incarnation(cards):
    s=game(cards)
    source=suspend(s,'Deep-Sea Kraken')
    shock=put(s,'Shock','hand','p2')
    mana(s,pid='p2',R=1)
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=shock.id,targets=['p3'],sources=[])
    wait_priority(s,'p1')
    spell=put(s,"Venser's Diffusion",'hand')
    mana(s,C=2,U=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[source.id],sources=[])
    old=s.state.rules.object_id(source.id)
    for _ in range(12):
        if s.state.cards[source.id].zone=='p1:hand':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert s.state.cards[source.id].zone=='p1:hand'
    source=put(s,'Deep-Sea Kraken','exile')
    act(s,'p1',type='set_counter',card_id=source.id,kind='time',value=9)
    assert s.state.rules.object_id(source.id)!=old
    settle(s)
    assert s.state.cards[source.id].counters['time']==9
    roundtrip(s)


def test_spell_copy_selects_its_counter_kind_independently_at_resolution(cards):
    s=game(cards)
    target=put(s,'Grizzly Bears','battlefield')
    for kind in ['charge','+1/+1']:
        act(s,'p1',type='set_counter',card_id=target.id,kind=kind,value=1)
    original=put(s,'Clockspinning','hand')
    mana(s,U=1)
    act(s,'p1',type='cast_spell',card_id=original.id,targets=[target.id],sources=[])
    copyspell=put(s,'Reverberate','hand','p2')
    mana(s,pid='p2',R=2)
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=copyspell.id,targets=[original.id],sources=[])
    settle(s)
    if s.state.rules.decision and 'keep' in {o.id for o in s.state.rules.decision.options}:
        choose(s,'keep')
    assert s.state.rules.decision.player=='p2'
    choose(s,'charge')
    choose(s,'add')
    choose(s,'+1/+1')
    choose(s,'remove')
    assert s.state.cards[target.id].counters.get('charge')==2
    assert not s.state.cards[target.id].counters.get('+1/+1')
    roundtrip(s)
