"""Actual mill receipts defer reanimation targets to their native reflexive trigger."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/reflexive_mill54_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='rm54',number=str(i),**{k:v for k,v in c.items() if k not in ('name','set_code')})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()

@pytest.mark.parametrize('name', ['Primal Witchstalker','Yathan Roadwatcher'])
def test_actual_cast_mills_before_reflexive_targets_and_returns_newly_milled_card(cards,tmp_path,name):
    names=[name,'Grizzly Bears','Llanowar Elves','Sol Ring','Forest']
    s=table(cards,names,names,names)
    to_phase(s,'main1',1)
    targets=[put(s,n,'hand') for n in ['Grizzly Bears','Llanowar Elves','Sol Ring','Forest']]
    act(s,'p1',type='move',card_ids=[c.id for c in targets],to={'player':'p1','zone':'library'},index=0)
    source=put(s,name,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'W':10,'U':10,'B':10,'R':10,'G':10,'C':10})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d is not None, s.state.model_dump_json()
    assert all(c.zone=='p1:graveyard' for c in targets)
    wanted=targets[3] if name=='Primal Witchstalker' else targets[0]
    assert wanted.id in [o.id for o in d.options]
    import subprocess
    import sys
    saved=tmp_path/'pending-reflexive.json'
    saved.write_text(s.state.model_dump_json())
    code=r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_placements import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
target,name=sys.argv[3:5]
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=[target])
settle(s)
assert s.state.cards[target].zone=='p1:battlefield'
assert s.state.cards[target].tapped==(name=='Primal Witchstalker')
roundtrip(s)
repo.close()
"""
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),wanted.id,name],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[wanted.id])
    settle(s)
    assert wanted.zone=='p1:battlefield'
    assert wanted.tapped == (name=='Primal Witchstalker')
    roundtrip(s)


def chosen(s, cid):
    d=s.state.rules.decision
    assert d is not None and cid in [o.id for o in d.options]
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[cid])
    settle(s)


def cast(s,name):
    source=put(s,name,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'W':10,'U':10,'B':10,'R':10,'G':10,'C':10})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    return source


def setup_extra(cards,name):
    names=[name,'Grizzly Bears','Llanowar Elves','Sol Ring','Forest','Serra Angel','Rest in Peace','Darksteel Colossus','Yathan Roadwatcher','Primal Witchstalker','Bruvac the Grandiloquent']
    s=table(cards,names,names,names)
    to_phase(s,'main1',1)
    return s


def library(s,names):
    found=[put(s,n,'hand') for n in names]
    act(s,'p1',type='move',card_ids=[c.id for c in found],to={'player':'p1','zone':'library'},index=0)
    return found


def test_wicks_patrol_native_receipt_sizes_from_current_graveyard_at_resolution(cards,tmp_path):
    from app.rules.plan import Plan
    s=setup_extra(cards,"Wick's Patrol")
    yard=library(s,['Grizzly Bears','Sol Ring','Forest'])
    target=put(s,'Serra Angel','battlefield','p2')
    cast(s,"Wick's Patrol")
    assert all(c.zone=='p1:graveyard' for c in yard)
    cold_target(s,cards,tmp_path,target,'pump')
    act(s,'p1',type='set_prefs',hold_priority=True)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
    act(s,'p1',type='move',card_ids=[yard[0].id],to={'player':'p1','zone':'exile'})
    settle(s)
    assert Plan(s.state,'p1',cards,None).ch(target).pt[0]==3
    to_phase(s,'end',1)
    to_phase(s,'upkeep',2)
    assert Plan(s.state,'p1',cards,None).ch(target).pt[0]==4
    roundtrip(s)


@pytest.mark.parametrize('recheck',[False,True])
def test_sigil_intervening_if_checks_creation_and_resolution(cards,tmp_path,recheck):
    from app.rules.plan import Plan
    s=setup_extra(cards,'Sigil of Myrkul')
    yard=[put(s,n,'graveyard') for n in ['Grizzly Bears','Llanowar Elves','Serra Angel']]
    library(s,['Yathan Roadwatcher'])
    target=put(s,'Darksteel Colossus','battlefield')
    cast(s,'Sigil of Myrkul')
    to_phase(s,'begin_combat',1)
    settle(s)
    assert s.state.rules.decision is not None
    if not recheck:
        cold_target(s,cards,tmp_path,target,'counter')
    act(s,'p1',type='set_prefs',hold_priority=True)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
    if recheck:
        act(s,'p1',type='move',card_ids=[yard[0].id],to={'player':'p1','zone':'exile'})
    settle(s)
    assert target.counters.get('+1/+1',0)==(0 if recheck else 1)
    assert ('deathtouch' in Plan(s.state,'p1',cards,None).ch(target).keywords)==(not recheck)
    roundtrip(s)


@pytest.mark.parametrize('count',[0,1,2,3])
def test_sigil_does_not_even_choose_target_below_four(cards,count):
    s=setup_extra(cards,'Sigil of Myrkul')
    for n in ['Grizzly Bears','Llanowar Elves','Serra Angel'][:count]:
        put(s,n,'graveyard')
    library(s,['Forest'])
    target=put(s,'Grizzly Bears','battlefield')
    cast(s,'Sigil of Myrkul')
    to_phase(s,'begin_combat',1)
    settle(s)
    assert s.state.rules.decision is None and not target.counters
    roundtrip(s)


def test_yathan_uncast_entry_does_not_mill_or_create_reflexive_trigger(cards):
    s=setup_extra(cards,'Yathan Roadwatcher')
    put(s,'Grizzly Bears','graveyard')
    before=list(s.state.zones['p1:library'])
    put(s,'Yathan Roadwatcher','battlefield')
    settle(s)
    assert s.state.zones['p1:library']==before and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('count',[0,1,2,3])
@pytest.mark.parametrize('rip',[False,True])
def test_mandatory_mill_zero_short_and_replaced_destinations(cards,count,rip):
    s=setup_extra(cards,"Wick's Patrol")
    target=put(s,'Serra Angel','battlefield','p2')
    put(s,'Grizzly Bears','graveyard')
    if rip:
        # Actual replacement applies, including its complete printed enters ability.
        source=put(s,'Rest in Peace','hand')
        act(s,'p1',type='add_mana',player='p1',mana={'W':1,'C':1})
        act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
        settle(s)
    ids=list(s.state.zones['p1:library'])
    act(s,'p1',type='move',card_ids=ids,to={'player':'p1','zone':'exile'})
    found=library(s,['Forest','Sol Ring','Grizzly Bears'][:count]) if count else []
    cast(s,"Wick's Patrol")
    if count==3:
        assert all(c.zone==('p1:exile' if rip else 'p1:graveyard') for c in found)
        assert s.state.rules.decision is not None
        chosen(s,target.id)
    else:
        assert s.state.rules.decision is None
    roundtrip(s)


def test_short_mill_remains_incomplete_even_when_card_self_shuffles(cards):
    s=setup_extra(cards,"Wick's Patrol")
    put(s,'Serra Angel','battlefield','p2')
    act(s,'p1',type='move',card_ids=list(s.state.zones['p1:library']),to={'player':'p1','zone':'exile'})
    library(s,['Darksteel Colossus'])
    cast(s,"Wick's Patrol")
    assert s.state.rules.decision is None
    assert len(s.state.zones['p1:library'])==1
    roundtrip(s)


def test_kravens_last_hunt_all_three_actual_chapters(cards,tmp_path):
    from app.rules.plan import Plan
    s=setup_extra(cards,"Kraven's Last Hunt")
    enemy=put(s,'Serra Angel','battlefield','p2')
    own=put(s,'Serra Angel','battlefield')
    yard=library(s,['Grizzly Bears','Llanowar Elves','Sol Ring','Forest','Rest in Peace'])
    source=cast(s,"Kraven's Last Hunt")
    assert all(c.zone=='p1:graveyard' for c in yard)
    cold_target(s,cards,tmp_path,enemy,'damage')
    chosen(s,enemy.id)
    assert enemy.damage==2
    to_phase(s,'main1',4)
    settle(s)
    chosen(s,own.id)
    assert Plan(s.state,'p1',cards,None).ch(own).pt==(6,6)
    to_phase(s,'main1',7)
    settle(s)
    chosen(s,yard[0].id)
    assert yard[0].zone=='p1:hand' and source.zone=='p1:graveyard'
    assert Plan(s.state,'p1',cards,None).ch(own).pt==(4,4)
    roundtrip(s)


def cold_target(s,cards,tmp_path,target,mode):
    import subprocess
    import sys
    saved=tmp_path/'pending-mill-target.json'
    saved.write_text(s.state.model_dump_json())
    code=r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_placements import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
target,mode=sys.argv[3:5]
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=[target])
settle(s)
c=s.state.cards[target]
if mode=='damage':assert c.damage==2
elif mode=='pump':assert Plan(s.state,'p1',repo,None).ch(c).pt==(2,2)
else:
 assert c.counters.get('+1/+1',0)==1
 assert 'deathtouch' in Plan(s.state,'p1',repo,None).ch(c).keywords
roundtrip(s)
repo.close()
"""
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),target.id,mode],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


def test_full_mill_counts_self_shuffle_modified_action(cards):
    s=setup_extra(cards,"Wick's Patrol")
    target=put(s,'Serra Angel','battlefield','p2')
    act(s,'p1',type='move',card_ids=list(s.state.zones['p1:library']),to={'player':'p1','zone':'exile'})
    library(s,['Darksteel Colossus','Forest','Sol Ring'])
    cast(s,"Wick's Patrol")
    assert len(s.state.zones['p1:library'])==1
    assert len(s.state.zones['p1:graveyard'])==2
    chosen(s,target.id)
    roundtrip(s)


@pytest.mark.parametrize('count',[5,6])
def test_bruvac_requires_complete_doubled_mill_amount(cards,count):
    s=setup_extra(cards,"Wick's Patrol")
    target=put(s,'Serra Angel','battlefield','p2')
    put(s,'Bruvac the Grandiloquent','battlefield','p2')
    act(s,'p1',type='move',card_ids=list(s.state.zones['p1:library']),to={'player':'p1','zone':'exile'})
    found=library(s,['Forest','Sol Ring','Grizzly Bears','Llanowar Elves','Serra Angel','Yathan Roadwatcher'][:count])
    cast(s,"Wick's Patrol")
    assert all(c.zone=='p1:graveyard' for c in found)
    if count==6:
        chosen(s,target.id)
    else:
        assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('name',["Kraven's Last Hunt","Wick's Patrol",'Sigil of Myrkul','Yathan Roadwatcher','Primal Witchstalker'])
def test_complete_canonical_mill_receipt_cards(cards,name):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'
