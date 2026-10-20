"""One native placement instruction survives table-action quantity bounds."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table

NAMES=['Yuna, Grand Summoner','Sol Ring','Grizzly Bears','Disenchant','Hardened Scales','All Will Be One','Doubling Season','Shalai, Voice of Plenty']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/large_counter_placement_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='lcp',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards,n,*,scales=False,damage=False,season=False):
    s=table(cards,NAMES,NAMES,NAMES)
    for pid in ['p1','p2','p3']:
        act(s,pid,type='set_prefs',hold_priority=True)
    put(s,'Yuna, Grand Summoner','battlefield')
    source=put(s,'Sol Ring','battlefield')
    target=put(s,'Grizzly Bears','battlefield')
    act(s,'p1',type='set_counter',card_id=source.id,kind='charge',value=n)
    if scales:
        put(s,'Hardened Scales','battlefield')
    if season:
        put(s,'Doubling Season','battlefield')
    if damage:
        put(s,'All Will Be One','battlefield')
    spell=put(s,'Disenchant','hand','p2')
    pay(s,'p2','Disenchant')
    act(s,'p1',type='pass_priority')
    act(s,'p2',type='cast_spell',card_id=spell.id,targets=[source.id],sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d and target.id in {o.id for o in d.options}
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
    settle(s)
    d=s.state.rules.decision
    assert d and 'yes' in {o.id for o in d.options}
    return s,source,target


def choose(s,value,finish=True):
    d=s.state.rules.decision
    assert d and value in {o.id for o in d.options}, (d.prompt if d else None,value)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
    if finish:
        settle(s)


@pytest.mark.parametrize('n',[1000,1005])
def test_yuna_large_lki_transfer_is_native_one_instruction(cards,n):
    s,source,target=game(cards,n)
    choose(s,'yes')
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[target.id].counters['+1/+1']==n
    roundtrip(s)


def test_hardened_scales_applies_once_before_chunked_commit(cards):
    s,_,target=game(cards,1005,scales=True)
    choose(s,'yes')
    assert s.state.cards[target.id].counters['+1/+1']==1006
    roundtrip(s)


def test_all_will_be_one_has_one_trigger_for_complete_replaced_amount(cards):
    s,_,target=game(cards,1005,scales=True,damage=True)
    act(s,'p1',type='set_life',player='p2',value=2000)
    choose(s,'yes')
    assert s.state.cards[target.id].counters['+1/+1']==1006
    d=s.state.rules.decision
    assert d and 'p2' in {o.id for o in d.options}
    # One target choice for one trigger, never one trigger per table-action chunk.
    choose(s,'p2')
    assert s.state.rules.decision is None and not s.state.zones['stack']
    assert s.state.players['p2'].life==994
    roundtrip(s)


def test_large_replacement_order_cold_resume_keeps_original_placement_group(cards,tmp_path):
    import subprocess
    import sys

    s,_,target=game(cards,1005,scales=True,season=True,damage=True)
    act(s,'p1',type='set_life',player='p2',value=4000)
    choose(s,'yes')
    d=s.state.rules.decision
    assert d and d.resume['step']=='replace_order'
    saved=tmp_path/'counter-group.json'
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
choices=0
for _ in range(50):
 d=s.state.rules.decision
 if d is not None:
  if d.resume['step']=='replace_order':
   option=d.options[0].id
  else:
   assert 'p2' in {o.id for o in d.options},d
   option='p2'
   choices+=1
  s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[option]})
 elif s.state.zones['stack']:
  s.perform(s.state.rules.priority,{'type':'pass_priority'})
 else:break
n=s.state.cards[target].counters['+1/+1']
assert n in (2011,2012),n
assert choices==1,choices
assert s.state.players['p2'].life==4000-n
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),target.id],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
