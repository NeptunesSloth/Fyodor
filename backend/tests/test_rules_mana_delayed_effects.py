"""Canonical payment-dependent effects reuse native casts, triggers and choices."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, history
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Chocobo Camp','Yuna, Grand Summoner','Solar Array','Brass Infiniscope','Rainbow Vale']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/mana_delayed_effects_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='sme',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/mana_delayed_effects_cards.json').read_text())]
    s=table(cards,names,names,names)
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    return s


def cast(s,name,pool,targets=(),pid='p1',**kwargs):
    wait_priority(s,pid)
    c=put(s,name,'hand',pid=pid)
    if pool:
        act(s,pid,type='add_mana',player=pid,mana=pool)
    act(s,pid,type='cast_spell',card_id=c.id,targets=list(targets),sources=[],**kwargs)
    return c


def answer(s,optional=True):
    for _ in range(100):
        settle(s)
        d=s.state.rules.decision
        if d is None:
            return
        ids={o.id for o in d.options}
        if 'keep' in ids:
            chosen=['keep']
        elif 'yes' in ids:
            chosen=['yes' if optional else 'no']
        elif 'pay' in ids and 'decline' in ids:
            chosen=['pay' if optional else 'decline']
        elif 'p3' in ids:
            chosen=['p3']
        else:
            chosen=[o.id for o in d.options][:max(1,d.min_choices)]
        act(s,d.player,type='choose',decision_id=d.id,option_ids=chosen)
    raise AssertionError('Decisions did not finish')


def drawn(s,pid='p1'):
    return history.log_for(Plan(s.state,'p1',s.cards,None)).drew.get(pid,0)


def permanents(s,word,pid='p1'):
    plan=Plan(s.state,pid,s.cards,None)
    return [c for c in s.state.cards.values() if c.zone==pid+':battlefield' and word in plan.ch(c).subtypes]


def setup(cards,name):
    s=game(cards)
    source=put(s,name,'battlefield')
    to_phase(s,'main1',4)
    return s,source


def activate(s,source,index=0,pool=None,targets=(),**kw):
    wait_priority(s,'p1')
    if pool:
        act(s,'p1',type='add_mana',player='p1',mana=pool)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index,targets=list(targets),**kw)


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('name,n',[('Chocobo Camp',1),('Yuna, Grand Summoner',2)])
def test_mana_creates_next_creature_entry_counter_watch(cards,name,n):
    s,source=setup(cards,name)
    activate(s,source,1 if name=='Chocobo Camp' else 0,**({'mana_choice':'G'} if name=='Yuna, Grand Summoner' else {}))
    assert not s.state.zones.get('stack',[]) and len(s.state.rules.delayed)==1
    spell=cast(s,'Storm Crow',{'U':1})
    roundtrip(s)
    answer(s)
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    assert s.state.cards[spell.id].counters.get('+1/+1')==n
    roundtrip(s)


def test_solar_array_grants_sunburst_before_artifact_creature_entry(cards):
    s,source=setup(cards,'Solar Array')
    activate(s,source,mana_choice='G')
    spell=cast(s,'Alloy Myr',{'U':1,'C':1})
    answer(s)
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    assert s.state.cards[spell.id].counters.get('+1/+1')==2
    assert 'sunburst' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[spell.id]).keywords
    roundtrip(s)


def test_brass_infiniscope_reads_cast_x_and_rounds_half_down(cards):
    s,source=setup(cards,'Brass Infiniscope')
    activate(s,source)
    before=drawn(s)
    cast(s,'Walking Ballista',{'C':4},x_value=3)
    answer(s)
    assert drawn(s)-before==1 and s.state.players['p1'].life==41
    roundtrip(s)


def test_rainbow_vale_gives_original_permanent_to_opponent_at_next_end(cards):
    s,source=setup(cards,'Rainbow Vale')
    activate(s,source,mana_choice='G')
    assert s.state.cards[source.id].controller=='p1' and len(s.state.rules.delayed)==1
    to_phase(s,'end',4)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and 'p2' in {o.id for o in d.options}
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['p2'])
    answer(s)
    assert s.state.cards[source.id].controller=='p2'
    roundtrip(s)


def resolve_watch(s):
    for _ in range(40):
        if len(s.state.zones.get('stack',[]))<=1:
            return
        d=s.state.rules.decision
        if d is not None:
            assert d.kind=='order'
            act(s,d.player,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options])
        else:
            act(s,s.state.rules.priority,type='pass_priority')
    raise AssertionError('Watch did not resolve')


@pytest.mark.parametrize('humility_after',[False,True])
def test_solar_array_sunburst_respects_prospective_ability_loss_timestamp(cards,humility_after):
    s,source=setup(cards,'Solar Array')
    if not humility_after:
        put(s,'Humility','battlefield')
    activate(s,source,mana_choice='G')
    spell=cast(s,'Alloy Myr',{'U':1,'C':1})
    resolve_watch(s)
    if humility_after:
        put(s,'Humility','battlefield')
    roundtrip(s)
    answer(s)
    assert s.state.cards[spell.id].counters.get('+1/+1',0)==(0 if humility_after else 2)
    assert ('sunburst' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[spell.id]).keywords)==(not humility_after)
    roundtrip(s)


def test_solar_array_noncreature_sunburst_uses_charge_counters(cards):
    s,source=setup(cards,'Solar Array')
    activate(s,source,mana_choice='G')
    spell=cast(s,'Sol Ring',{})
    answer(s)
    assert s.state.cards[spell.id].counters.get('charge')==1
    assert not s.state.cards[spell.id].counters.get('+1/+1')
    roundtrip(s)


def test_solar_array_granted_sunburst_is_not_copiable_and_original_keeps_it(cards):
    s,source=setup(cards,'Solar Array')
    activate(s,source,mana_choice='G')
    spell=cast(s,'Alloy Myr',{'U':1,'C':1})
    resolve_watch(s)
    cast(s,'Double Major',{'U':1,'G':1},[spell.id])
    answer(s)
    copies=[c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield' and Plan(s.state,'p1',s.cards,None).ch(c).name=='Alloy Myr']
    assert len(copies)==1 and not copies[0].counters
    assert 'sunburst' not in Plan(s.state,'p1',s.cards,None).ch(copies[0]).keywords
    assert s.state.cards[spell.id].counters.get('+1/+1')==2
    roundtrip(s)


def test_yuna_counts_every_counter_kind_on_departed_permanent_using_lki(cards):
    s,source=setup(cards,'Yuna, Grand Summoner')
    walker=cast(s,'Hangarback Walker',{'C':4},x_value=2)
    answer(s)
    bear=put(s,'Grizzly Bears','battlefield')
    act(s,'p1',type='counter',card_ids=[walker.id],kind='charge',delta=3)
    cast(s,'Lightning Bolt',{'R':1},[walker.id],pid='p2')
    for _ in range(40):
        settle(s)
        d=s.state.rules.decision
        if d is None:
            break
        ids={o.id for o in d.options}
        if d.kind=='order':
            choice=[o.id for o in d.options]
        else:
            choice=[bear.id] if bear.id in ids else ['yes'] if 'yes' in ids else [d.options[0].id]
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=choice)
    assert s.state.cards[walker.id].zone=='p1:graveyard'
    assert s.state.cards[bear.id].counters.get('+1/+1')==5
    roundtrip(s)


@pytest.mark.parametrize('x',[0,1,2,4])
def test_brass_actual_announced_x_zero_even_odd(cards,x):
    s,source=setup(cards,'Brass Infiniscope')
    activate(s,source)
    before=drawn(s)
    cast(s,'Walking Ballista',{'C':max(0,2*x-2)},x_value=x)
    answer(s)
    assert drawn(s)-before==1 and s.state.players['p1'].life==40+x//2
    roundtrip(s)


@pytest.mark.parametrize('counters',[0,3])
def test_yuna_noncreature_artifact_counter_gate_and_lki(cards,counters):
    s,_=setup(cards,'Yuna, Grand Summoner')
    ring=put(s,'Sol Ring','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    if counters:
        act(s,'p1',type='counter',card_ids=[ring.id],kind='charge',delta=counters)
    cast(s,'Shrapnel Blast',{'R':1,'C':1},['p2'],cost_choices=[{'component':0,'cards':[ring.id]}])
    for _ in range(30):
        settle(s)
        d=s.state.rules.decision
        if d is None:
            break
        ids={o.id for o in d.options}
        choice=[o.id for o in d.options] if d.kind=='order' else [bear.id] if bear.id in ids else ['yes'] if 'yes' in ids else [d.options[0].id]
        act(s,d.player,type='choose',decision_id=d.id,option_ids=choice)
    assert s.state.cards[ring.id].zone=='p1:graveyard'
    assert s.state.cards[bear.id].counters.get('+1/+1',0)==counters
    assert s.state.players['p2'].life==35
    roundtrip(s)


@pytest.mark.parametrize('gone',['blink','phased'])
def test_rainbow_old_source_cannot_transfer_after_blink_or_while_phased_out(cards,gone):
    s,source=setup(cards,'Rainbow Vale')
    activate(s,source,mana_choice='G')
    if gone=='blink':
        put(s,'Rainbow Vale','exile')
        put(s,'Rainbow Vale','battlefield')
    else:
        act(s,'p1',type='phase_shift',card_ids=[source.id],out=True)
    roundtrip(s)
    to_phase(s,'end',4)
    answer(s)
    assert s.state.cards[source.id].controller=='p1'
    assert not s.state.rules.delayed
    roundtrip(s)


def test_rainbow_delayed_controller_keeps_own_opponents_after_source_control_changes(cards):
    s,source=setup(cards,'Rainbow Vale')
    activate(s,source,mana_choice='G')
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    to_phase(s,'end',4)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and {o.id for o in d.options}=={'p2','p3'}
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['p3'])
    answer(s)
    assert s.state.cards[source.id].controller=='p3'
    roundtrip(s)


def test_brass_countered_spell_and_departed_source_preserve_event_x_through_cold_draw_choice(cards,tmp_path):
    import subprocess
    import sys

    s,source=setup(cards,'Brass Infiniscope')
    activate(s,source)
    put(s,'Abundance','battlefield')
    before=drawn(s)
    spell=cast(s,'Walking Ballista',{'C':8},x_value=5)
    cast(s,'Counterspell',{'U':2},[spell.id],pid='p2')
    put(s,'Brass Infiniscope','graveyard')
    settle(s)
    d=s.state.rules.decision
    assert d is not None and 'decline' in {o.id for o in d.options}
    assert s.state.players['p1'].life==40 and s.state.cards[spell.id].zone=='p1:graveyard'
    roundtrip(s)
    saved=tmp_path/'brass-x-delayed.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle
from tests.test_rules_mana_delayed_effects import drawn
save,db,before=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['decline']})
settle(s)
assert drawn(s)-int(before)==1 and s.state.players['p1'].life==42
assert not s.state.rules.decision and not s.state.zones.get('stack',[])
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),str(before)],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['decline'])
    answer(s)
    assert drawn(s)-before==1 and s.state.players['p1'].life==42
    roundtrip(s)
