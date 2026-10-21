"""Canonical counter follow-through uses paid facts, actual removals, and source LKI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Dawn of a New Age','Decree of Silence','Lost Isle Calling','Blademane Baku','Magmatic Sprinter']
EXTRA=['Grizzly Bears','Shalai, Voice of Plenty','Shock','Supreme Verdict','Doubling Season','Solemnity','Rings of Brighthearth','Reverberate','Narset, Parter of Veils','Abundance','Opt','Necrotic Ooze','Reach Through Mists','Forest','Island']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/counter_followthrough_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='cft',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    ns=[*NAMES,*EXTRA]
    return table(cards,ns,ns,ns)


def priority(s,pid):
    for _ in range(12):
        if s.state.rules.priority==pid:
            return
        assert s.state.rules.decision is None
        act(s,s.state.rules.priority,type='pass_priority')
    raise AssertionError('priority not reached')


def cast(s,name,pid='p1',targets=(),finish=True):
    c=put(s,name,'hand',pid)
    pay(s,pid,name)
    priority(s,pid)
    act(s,pid,type='cast_spell',card_id=c.id,targets=list(targets),sources=[])
    if finish:
        settle(s)
    return c


def counters(s,c,n,kind):
    act(s,'p1',type='set_counter',card_id=c.id,kind=kind,value=n)


def choose(s,value):
    d=s.state.rules.decision
    assert d and value in {o.id for o in d.options},(d.prompt if d else None,value)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
    settle(s)


def ch(s,c):
    return Plan(s.state,'p1',s.cards,None).ch(s.state.cards[c.id])


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('hopes,drawn,gained,alive',[(0,0,4,False),(1,1,4,False),(2,1,0,True)])
def test_dawn_actual_removal_gates_only_draw_and_zero_check_is_independent(cards,hopes,drawn,gained,alive):
    s=game(cards)
    c=put(s,NAMES[0],'battlefield')
    counters(s,c,hopes,'hope')
    before=len(s.state.zones['p1:hand'])
    to_phase(s,'end')
    settle(s)
    assert len(s.state.zones['p1:hand'])==before+drawn
    assert s.state.players['p1'].life==40+gained
    assert s.state.cards[c.id].zone==('p1:battlefield' if alive else 'p1:graveyard')
    roundtrip(s)


def test_dawn_native_entry_counter_count_and_endstep_draw(cards):
    s=game(cards)
    put(s,'Grizzly Bears','battlefield')
    put(s,'Shalai, Voice of Plenty','battlefield')
    c=cast(s,NAMES[0])
    assert s.state.cards[c.id].counters['hope']==2
    to_phase(s,'end')
    settle(s)
    assert s.state.cards[c.id].counters['hope']==1
    roundtrip(s)


def test_dawn_new_incarnation_not_sacrificed_or_removed_by_old_trigger(cards):
    s=game(cards)
    c=put(s,NAMES[0],'battlefield')
    counters(s,c,1,'hope')
    to_phase(s,'end')
    put(s,NAMES[0],'exile')
    put(s,NAMES[0],'battlefield')
    counters(s,c,5,'hope')
    before=len(s.state.zones['p1:hand'])
    settle(s)
    assert len(s.state.zones['p1:hand'])==before
    assert s.state.cards[c.id].counters['hope']==5 and s.state.cards[c.id].zone=='p1:battlefield'
    assert s.state.players['p1'].life==40
    roundtrip(s)


@pytest.mark.parametrize('uncounterable',[False,True])
def test_decree_third_counter_sacrifices_even_if_spell_cannot_be_countered(cards,uncounterable):
    s=game(cards)
    c=put(s,NAMES[1],'battlefield')
    counters(s,c,2,'depletion')
    bear=put(s,'Grizzly Bears','battlefield')
    if uncounterable:
        to_phase(s,'main1',turn=2)
    spell=cast(s,'Supreme Verdict' if uncounterable else 'Shock','p2',targets=[] if uncounterable else ['p1'])
    assert s.state.cards[c.id].zone=='p1:graveyard'
    assert s.state.cards[spell.id].zone=='p2:graveyard'
    assert s.state.players['p1'].life==40
    assert s.state.cards[bear.id].zone==('p1:graveyard' if uncounterable else 'p1:battlefield')
    roundtrip(s)


def test_decree_counter_replacement_reaches_threshold_early(cards):
    s=game(cards)
    c=put(s,NAMES[1],'battlefield')
    counters(s,c,1,'depletion')
    put(s,'Doubling Season','battlefield')
    cast(s,'Shock','p3',targets=['p1'])
    assert s.state.cards[c.id].zone=='p1:graveyard' and s.state.players['p1'].life==40
    roundtrip(s)


@pytest.mark.parametrize('verse',[0,6,7])
def test_lost_isle_actual_exile_cost_draw_and_original_counter_threshold(cards,verse):
    s=game(cards)
    c=put(s,NAMES[2],'battlefield')
    counters(s,c,verse,'verse')
    act(s,'p1',type='add_mana',mana={'C':4,'U':2})
    before=len(s.state.zones['p1:hand'])
    act(s,'p1',type='activate_ability',card_id=c.id,ability=ability_index(s,c,'Draw a card for each'),sources=[])
    assert s.state.cards[c.id].zone=='p1:exile' and not s.state.cards[c.id].counters
    settle(s)
    assert len(s.state.zones['p1:hand'])==before+verse
    assert len(s.state.rules.extra_turns)==int(verse>=7)
    assert not mana_pool(s)
    roundtrip(s)


@pytest.mark.parametrize('x',[0,3])
def test_baku_real_paid_counter_count_pumps_twice_x_until_eot(cards,x):
    s=game(cards)
    c=put(s,NAMES[3],'battlefield')
    counters(s,c,5,'ki')
    act(s,'p1',type='add_mana',mana={'C':1})
    act(s,'p1',type='activate_ability',card_id=c.id,ability=ability_index(s,c,'For each counter'),x_value=x,sources=[])
    assert s.state.cards[c.id].counters['ki']==5-x
    settle(s)
    assert ch(s,c).pt==(1+2*x,1)
    to_phase(s,'main1',turn=2)
    assert ch(s,c).pt==(1,1)
    roundtrip(s)


def test_baku_rings_copy_uses_same_original_payment_once(cards):
    s=game(cards)
    c=put(s,NAMES[3],'battlefield')
    put(s,'Rings of Brighthearth','battlefield')
    counters(s,c,5,'ki')
    act(s,'p1',type='add_mana',mana={'C':3})
    act(s,'p1',type='activate_ability',card_id=c.id,ability=ability_index(s,c,'For each counter'),x_value=3,sources=[])
    settle(s)
    choose(s,'pay')
    if s.state.rules.decision:
        choose(s,'keep')
    assert s.state.cards[c.id].counters['ki']==2
    assert ch(s,c).pt==(13,1)
    roundtrip(s)


@pytest.mark.parametrize('oil,payit',[(1,False),(2,False),(2,True),(4,True)])
def test_sprinter_native_whole_optional_counter_cost_or_return(cards,oil,payit):
    s=game(cards)
    c=put(s,NAMES[4],'battlefield')
    counters(s,c,oil,'oil')
    to_phase(s,'end')
    settle(s)
    if oil>=2:
        choose(s,'pay' if payit else 'decline')
    else:
        assert not s.state.rules.decision
    assert s.state.cards[c.id].zone==('p1:battlefield' if payit else 'p1:hand')
    if payit:
        assert s.state.cards[c.id].counters.get('oil',0)==oil-2
    roundtrip(s)


def test_lost_isle_seven_counter_threshold_ignores_draws_prevented_by_real_narset(cards):
    s=game(cards)
    c=put(s,'Lost Isle Calling','battlefield')
    counters(s,c,7,'verse')
    to_phase(s,'main1',turn=2)
    cast(s,'Narset, Parter of Veils','p2')
    to_phase(s,'main1',turn=4)
    before=len(s.state.zones['p1:hand'])
    act(s,'p1',type='add_mana',mana={'C':4,'U':2})
    act(s,'p1',type='activate_ability',card_id=c.id,ability=ability_index(s,c,'Draw a card for each'),sources=[])
    settle(s)
    assert len(s.state.zones['p1:hand'])==before
    assert len(s.state.rules.extra_turns)==1
    roundtrip(s)


def test_baku_actual_arcane_cast_trigger_then_remove_paid_counter(cards):
    s=game(cards)
    c=put(s,'Blademane Baku','battlefield')
    cast(s,'Reach Through Mists')
    choose(s,'yes')
    assert s.state.cards[c.id].counters['ki']==1
    act(s,'p1',type='add_mana',mana={'C':1})
    act(s,'p1',type='activate_ability',card_id=c.id,ability=ability_index(s,c,'For each counter'),x_value=1,sources=[])
    settle(s)
    assert not s.state.cards[c.id].counters and ch(s,c).pt==(3,1)
    roundtrip(s)


def test_borrowed_baku_ability_uses_actual_ooze_paid_quantity_and_source(cards):
    s=game(cards)
    lender=put(s,'Blademane Baku','graveyard')
    c=put(s,'Necrotic Ooze','battlefield')
    counters(s,c,3,'ki')
    act(s,'p1',type='add_mana',mana={'C':1})
    act(s,'p1',type='activate_ability',card_id=c.id,ability=ability_index(s,c,'For each counter'),x_value=3,sources=[])
    settle(s)
    assert not s.state.cards[c.id].counters and not s.state.cards[lender.id].counters
    assert ch(s,c).pt==(10,3)
    roundtrip(s)


def test_sprinter_actual_entry_targets_self_then_pays_entire_oil_upkeep(cards):
    s=game(cards)
    c=cast(s,'Magmatic Sprinter')
    choose(s,c.id)
    assert s.state.cards[c.id].counters['oil']==2
    to_phase(s,'end')
    settle(s)
    choose(s,'pay')
    assert s.state.cards[c.id].zone=='p1:battlefield' and not s.state.cards[c.id].counters
    roundtrip(s)


def test_dawn_draw_replacement_saved_then_tail_still_sacrifices_and_gains(cards,tmp_path):
    import subprocess
    import sys

    from tests.test_rules_abundance import set_library

    s=game(cards)
    c=put(s,'Dawn of a New Age','battlefield')
    counters(s,c,1,'hope')
    put(s,'Abundance','battlefield')
    top=set_library(s,['Forest','Grizzly Bears'])
    to_phase(s,'end')
    settle(s)
    d=s.state.rules.decision
    assert d and 'decline' in {o.id for o in d.options}
    choose(s,next(o.id for o in d.options if o.id!='decline'))
    assert {o.id for o in s.state.rules.decision.options}=={'land','nonland'}
    saved=tmp_path/'dawn.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,db,source,land=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['land']})
for _ in range(12):
 if not s.state.zones['stack']:break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.cards[source].zone=='p1:graveyard'
assert s.state.players['p1'].life==44
assert s.state.cards[land].zone=='p1:hand'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),c.id,top[0]],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('name,kind,n',[('Lost Isle Calling','verse',7),('Blademane Baku','ki',3)])
def test_paid_source_snapshot_and_scalar_effect_resolve_after_cold_load(cards,tmp_path,name,kind,n):
    import subprocess
    import sys

    s=game(cards)
    c=put(s,name,'battlefield')
    counters(s,c,n,kind)
    act(s,'p1',type='set_prefs',hold_priority=True)
    if kind=='verse':
        act(s,'p1',type='add_mana',mana={'C':4,'U':2})
        kwargs={}
        text='Draw a card for each'
    else:
        act(s,'p1',type='add_mana',mana={'C':1})
        kwargs={'x_value':3}
        text='For each counter'
    act(s,'p1',type='activate_ability',card_id=c.id,ability=ability_index(s,c,text),sources=[],**kwargs)
    saved=tmp_path/'counter-paid.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
save,db,source,kind=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
before=len(s.state.zones['p1:hand'])
for _ in range(15):
 if not s.state.zones['stack']:break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
if kind=='verse':
 assert len(s.state.zones['p1:hand'])==before+7
 assert len(s.state.rules.extra_turns)==1
 assert s.state.cards[source].zone=='p1:exile'
else:
 assert Plan(s.state,'p1',repo,None).ch(s.state.cards[source]).pt==(7,1)
 assert not s.state.cards[source].counters
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),c.id,kind],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_lost_isle_actual_scry_adds_verse_then_spends_it_for_draw(cards):
    s=game(cards)
    c=put(s,'Lost Isle Calling','battlefield')
    cast(s,'Opt')
    d=s.state.rules.decision
    assert d and d.resume['step']=='look'
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
    settle(s)
    assert s.state.cards[c.id].counters['verse']==1
    before=len(s.state.zones['p1:hand'])
    act(s,'p1',type='add_mana',mana={'C':4,'U':2})
    act(s,'p1',type='activate_ability',card_id=c.id,ability=ability_index(s,c,'Draw a card for each'),sources=[])
    settle(s)
    assert len(s.state.zones['p1:hand'])==before+1
    assert not s.state.rules.extra_turns
    roundtrip(s)


def test_sprinter_old_upkeep_cannot_pay_from_or_return_new_object(cards):
    s=game(cards)
    c=put(s,'Magmatic Sprinter','battlefield')
    counters(s,c,2,'oil')
    to_phase(s,'end')
    put(s,'Magmatic Sprinter','exile')
    put(s,'Magmatic Sprinter','battlefield')
    counters(s,c,5,'oil')
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[c.id].zone=='p1:battlefield' and s.state.cards[c.id].counters['oil']==5
    roundtrip(s)


def test_decree_departure_does_not_stop_original_spell_counter(cards):
    s=game(cards)
    c=put(s,'Decree of Silence','battlefield')
    act(s,'p2',type='set_prefs',hold_priority=True)
    spell=cast(s,'Shock','p2',targets=['p1'],finish=False)
    put(s,'Decree of Silence','graveyard')
    settle(s)
    assert s.state.cards[spell.id].zone=='p2:graveyard'
    assert s.state.players['p1'].life==40
    assert s.state.cards[c.id].zone=='p1:graveyard'
    roundtrip(s)
