"""Canonical library and parity choices reuse native continuations."""
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
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_mana_delayed_effects import answer, cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/resolved_library_choice_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='nac',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/resolved_library_choice_cards.json').read_text())]
    s=table(cards,names,names,names)
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    to_phase(s,'main1',5)
    return s


NAMES=['Abundant Harvest','Vexing Arcanix',"Zimone's Hypothesis"]


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def top(s,name,pid='p1'):
    c=put(s,name,'hand',pid=pid)
    act(s,pid,type='move',card_ids=[c.id],to={'player':pid,'zone':'library'},position='top')
    return c


@pytest.mark.parametrize('kind',['land','nonland'])
def test_harvest_actual_choice_and_found_card(cards,kind):
    s=game(cards)
    found=top(s,'Forest' if kind=='land' else 'Storm Crow')
    other=top(s,'Storm Crow' if kind=='land' else 'Forest')
    # Sorcery belongs to the active player on turn five.
    found=top(s,found.name,pid='p2')
    other=top(s,other.name,pid='p2')
    cast(s,'Abundant Harvest',{'G':1},pid='p2')
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[kind])
    answer(s)
    assert s.state.cards[found.id].zone=='p2:hand'
    assert s.state.zones['p2:library'][-1]==other.id
    roundtrip(s)


@pytest.mark.parametrize('correct',[True,False])
def test_arcanix_actual_name_then_hand_or_graveyard_damage(cards,correct):
    s=game(cards)
    artifact=put(s,'Vexing Arcanix','battlefield')
    revealed=top(s,'Forest',pid='p2')
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'C':3})
    act(s,'p1',type='activate_ability',card_id=artifact.id,ability=0,targets=['p2'],sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.player=='p2'
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[],name='Forest' if correct else 'Storm Crow')
    answer(s)
    assert s.state.cards[revealed.id].zone==('p2:hand' if correct else 'p2:graveyard')
    assert s.state.players['p2'].life==(40 if correct else 38)
    roundtrip(s)


@pytest.mark.parametrize('add_counter',[True,False])
def test_zimone_optional_nontarget_counter_then_mandatory_parity_bounce(cards,add_counter):
    s=game(cards)
    creature=put(s,'Slippery Bogle','battlefield',pid='p3')
    even_creature=put(s,'Isamaru, Hound of Konda','battlefield')
    cast(s,"Zimone's Hypothesis",{'U':2,'C':3},pid='p2')
    settle(s)
    d=s.state.rules.decision
    assert d is not None and creature.id in {o.id for o in d.options}
    assert d.min_choices==0
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[creature.id] if add_counter else [])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and 'Even' in {o.id for o in d.options}
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['Even'])
    answer(s)
    assert s.state.cards[creature.id].zone==('p3:hand' if add_counter else 'p3:battlefield')
    assert s.state.cards[even_creature.id].zone=='p1:hand'
    roundtrip(s)


def test_harvest_missing_kind_returns_all_revealed_without_drawing(cards):
    s=game(cards)
    spell=put(s,'Abundant Harvest','hand',pid='p2')
    remove=[c for c in s.state.zones['p2:library'] if 'Land' not in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[c]).types]
    if remove:
        act(s,'p2',type='move',card_ids=remove,to={'player':'p2','zone':'exile'})
    before=set(s.state.zones['p2:library'])
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'G':1})
    act(s,'p2',type='cast_spell',card_id=spell.id,sources=[],targets=[])
    settle(s)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['nonland'])
    answer(s)
    assert set(s.state.zones['p2:library'])==before
    assert s.state.players['p2'].life==40
    roundtrip(s)


def test_arcanix_empty_library_still_deals_wrong_guess_damage(cards):
    s=game(cards)
    artifact=put(s,'Vexing Arcanix','battlefield')
    act(s,'p2',type='move',card_ids=list(s.state.zones['p2:library']),to={'player':'p2','zone':'exile'})
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'C':3})
    act(s,'p1',type='activate_ability',card_id=artifact.id,ability=0,targets=['p2'],sources=[])
    settle(s)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[],name='Forest')
    answer(s)
    assert s.state.players['p2'].life==38 and not s.state.players['p2'].left
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_actual_choice_fresh_process_resume(cards,tmp_path,name):
    import subprocess
    import sys
    s=game(cards)
    if name=="Zimone's Hypothesis":
        watched=put(s,'Slippery Bogle','battlefield',pid='p3')
        cast(s,name,{'U':2,'C':3},pid='p2')
        wanted='p3:hand'
    else:
        watched=top(s,'Forest',pid='p2')
        wanted='p2:hand'
        if name=='Abundant Harvest':
            cast(s,name,{'G':1},pid='p2')
        else:
            artifact=put(s,name,'battlefield')
            wait_priority(s,'p1')
            act(s,'p1',type='add_mana',player='p1',mana={'C':3})
            act(s,'p1',type='activate_ability',card_id=artifact.id,ability=0,targets=['p2'],sources=[])
    settle(s)
    assert s.state.rules.decision is not None
    saved=tmp_path/'choice.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle
from tests.test_rules_mana_delayed_effects import answer
save,db,name,cid,wanted=sys.argv[1:]
r=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=r)
d=s.state.rules.decision
if name=='Abundant Harvest':
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['land']})
elif name=='Vexing Arcanix':
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[],'name':'Forest'})
else:
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[cid]})
 settle(s)
 d=s.state.rules.decision
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['Even']})
answer(s)
assert s.state.cards[cid].zone==wanted
assert not s.state.rules.decision
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
r.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),name,watched.id,wanted],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
