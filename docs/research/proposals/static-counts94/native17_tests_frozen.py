"""Conditional attachment and Army animation use native continuous effects."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Light from Within', 'Umbra Stalker', 'Diligent Zookeeper', 'Dark Matter Manipulator', 'Enemy of Enlightenment']
DATA = json.loads((Path(__file__).parent/'fixtures/static_counts94_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Arcane Adaptation']*11


@pytest.fixture()
def cards(settings):
    base = {c['name']:c for c in fixture_cards()}
    for i,c in enumerate(DATA):
        base[c['name']]=card(c['name'],number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    s=table(cards,ALL,ALL,ALL)
    to_phase(s,'main1',1)
    return s


def cast(s,name,pid='p1',targets=(),**kwargs):
    candidates=[c for c in s.state.cards.values() if c.name==name and c.owner==pid and c.zone not in (f'{pid}:battlefield','stack') and c.ability is None]
    source=next((c for c in candidates if c.zone==f'{pid}:hand'),candidates[0])
    if source.zone!=f'{pid}:hand':
        act(s,pid,type='move',card_ids=[source.id],to={'player':pid,'zone':'hand'})
    mana(s,pid,C=20,W=10,U=10,B=10,R=10,G=10)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=list(targets),sources=[],**kwargs)
    settle(s)
    return source


def ch(s,source):
    return Plan.view(s.state,'p1',s.cards).ch(s.state.cards[source.id])



def empty_hands(s,*players):
    for pid in players:
        hand=list(s.state.zones.get(f'{pid}:hand',[]))
        if hand:
            act(s,pid,type='move',card_ids=hand,to={'player':pid,'zone':'library'})


@pytest.mark.parametrize('name',NAMES)
def test_native_canonical_whole_cast(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'
    s=game(cards)
    empty_hands(s,'p2','p3')
    put(s,'Dark Ritual','graveyard')
    source=cast(s,name)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)


def test_native_light_recipient_costs_hybrids_and_rules_text_not_counted(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    angel=put(s,'Serra Angel','battlefield')
    fox=put(s,'Eight-and-a-Half-Tails','battlefield')
    hybrid=put(s,'Divinity of Pride','battlefield')
    cast(s,'Light from Within')
    assert ch(s,bear).pt==(2,2)
    assert ch(s,angel).pt==(6,6)
    assert ch(s,fox).pt==(4,4)
    assert ch(s,hybrid).pt==(13,13)
    act(s,'p1',type='set_controller',card_ids=[angel.id],player='p2')
    assert ch(s,angel).pt==(4,4)
    act(s,'p2',type='set_controller',card_ids=[angel.id],player='p1')
    assert ch(s,angel).pt==(6,6)
    roundtrip(s)


def test_native_light_actual_copy_changes_each_recipient_mana_cost(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    hybrid=put(s,'Divinity of Pride','battlefield')
    cast(s,'Light from Within')
    act(s,'p1',type='counter',card_ids=[bear.id],kind='+1/+1',delta=2)
    assert ch(s,bear).pt==(4,4)
    cast(s,'Mirrorweave',targets=[hybrid.id])
    assert ch(s,bear).mana_cost==ch(s,hybrid).mana_cost and ch(s,bear).pt==(15,15)
    to_phase(s,'main1',2)
    assert ch(s,bear).name=='Grizzly Bears' and ch(s,bear).pt==(4,4)
    roundtrip(s)


def test_native_umbra_cda_counts_cost_symbols_all_zones_including_self(cards):
    s=game(cards)
    stalker=put(s,'Umbra Stalker','hand')
    put(s,'Dismember','graveyard')
    put(s,'Divinity of Pride','graveyard')
    put(s,'Reaper King','graveyard')
    put(s,'Transguild Courier','graveyard')
    put(s,'Dark Ritual','graveyard','p2')
    assert ch(s,stalker).pt==(8,8)
    source=cast(s,'Umbra Stalker')
    assert ch(s,source).pt==(8,8)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    assert ch(s,source).pt==(11,11)
    cast(s,'Raise Dead',targets=[source.id])
    assert s.state.cards[source.id].zone=='p1:hand' and ch(s,source).pt==(9,9)
    roundtrip(s)


def test_native_umbra_actual_graveyard_clear_dies_then_counts_own_cost(cards):
    s=game(cards)
    put(s,'Dark Ritual','graveyard')
    source=cast(s,'Umbra Stalker')
    crypt=cast(s,"Tormod's Crypt")
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=crypt.id,ability=0,targets=['p1'],sources=[])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard' and ch(s,source).pt==(3,3)
    roundtrip(s)


def test_native_manipulator_real_mill_floor_boundaries_and_control(cards):
    s=game(cards)
    for name in ['Divinity of Pride','Serra Angel','Eight-and-a-Half-Tails','Reaper King']:
        put(s,name,'graveyard')
    for name in ['Dark Ritual','Reach Through Mists','Tome Scour']:
        put(s,name,'hand')
    source=cast(s,'Dark Matter Manipulator')
    assert len(s.state.zones['p1:graveyard'])==7
    base=int(cards.resolve('Dark Matter Manipulator')['power'])
    assert ch(s,source).pt[0]==base+2
    removed=s.state.zones['p1:graveyard'][0]
    act(s,'p1',type='move',card_ids=[removed],to={'player':'p1','zone':'library'})
    assert ch(s,source).pt[0]==base
    cast(s,'Reach Through Mists')
    assert len(s.state.zones['p1:graveyard'])==7 and ch(s,source).pt[0]==base+2
    cast(s,'Tome Scour',targets=['p1'])
    assert len(s.state.zones['p1:graveyard'])==13 and ch(s,source).pt[0]==base+2
    cast(s,'Dark Ritual')
    assert len(s.state.zones['p1:graveyard'])==14 and ch(s,source).pt[0]==base+4
    act(s,'p1',type='counter',card_ids=[source.id],kind='+1/+1',delta=1)
    assert ch(s,source).pt[0]==base+5
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    assert ch(s,source).pt[0]==base+1
    roundtrip(s)


def choose_type(s,kind):
    d=s.state.rules.decision
    assert d is not None and kind in [o.id for o in d.options]
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[kind])
    settle(s)


def test_native_zookeeper_real_type_grants_cap_human_exclusion_and_layers(cards,tmp_path):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    zoo=cast(s,'Diligent Zookeeper')
    assert ch(s,bear).pt==(3,3)
    species=['Elf','Goblin','Merfolk','Wizard','Warrior','Soldier','Cleric','Rogue','Knight','Shaman','Beast']
    for i,kind in enumerate(species):
        cast(s,'Arcane Adaptation')
        choose_type(s,kind)
        assert ch(s,bear).pt==(2+min(2+i,10),2+min(2+i,10))
    act(s,'p1',type='counter',card_ids=[bear.id],kind='+1/+1',delta=1)
    assert ch(s,bear).pt==(13,13)
    run_cold(s,tmp_path,'cap',{'bear':bear.id})
    cast(s,'Giant Growth',targets=[bear.id])
    assert ch(s,bear).pt==(16,16)
    act(s,'p1',type='set_controller',card_ids=[zoo.id],player='p2')
    assert ch(s,bear).pt==(6,6)
    act(s,'p2',type='set_controller',card_ids=[zoo.id],player='p1')
    assert ch(s,bear).pt==(16,16)
    human=cast(s,'Arcane Adaptation')
    choose_type(s,'Human')
    assert ch(s,bear).pt==(6,6)
    cast(s,'Disenchant',targets=[human.id])
    assert ch(s,bear).pt==(16,16)
    to_phase(s,'main1',2)
    assert ch(s,bear).pt==(13,13)
    roundtrip(s)


def test_native_enemy_counts_all_opponents_and_current_controller(cards):
    s=game(cards)
    empty_hands(s,'p1','p2','p3')
    source=cast(s,'Enemy of Enlightenment')
    put(s,'Dark Ritual','hand')
    put(s,'Grizzly Bears','hand','p2')
    put(s,'Llanowar Elves','hand','p2')
    put(s,'Serra Angel','hand','p3')
    assert ch(s,source).pt==(2,2)
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    assert ch(s,source).pt==(3,3)
    act(s,'p3',type='concede')
    assert ch(s,source).pt==(4,4)
    roundtrip(s)


def test_native_enemy_upkeep_private_apnap_choices_discard_simultaneously(cards):
    s=game(cards)
    empty_hands(s,'p1','p2','p3')
    source=cast(s,'Enemy of Enlightenment')
    to_phase(s,'end',3)
    empty_hands(s,'p1','p2','p3')
    for pid in ['p1','p2','p3']:
        put(s,'Grizzly Bears','hand',pid)
        put(s,'Llanowar Elves','hand',pid)
    assert ch(s,source).pt==(1,1)
    before={pid:list(s.state.zones[f'{pid}:hand']) for pid in ['p1','p2','p3']}
    to_phase(s,'upkeep',4)
    settle(s)
    picked=[]
    for pid in ['p1','p2','p3']:
        d=s.state.rules.decision
        assert d is not None and d.resume['step']=='discard' and d.player==pid
        assert all(list(s.state.zones[f'{p}:hand'])==ids for p,ids in before.items())
        chosen=d.options[0].id
        picked.append(chosen)
        act(s,pid,type='choose',decision_id=d.id,option_ids=[chosen])
        settle(s)
    assert all(s.state.cards[cid].zone.endswith(':graveyard') for cid in picked)
    assert all(len(s.state.zones[f'{pid}:hand'])==1 for pid in ['p1','p2','p3'])
    assert ch(s,source).pt==(3,3)
    roundtrip(s)


def test_native_enemy_transient_zero_during_real_draw_then_discard_survives(cards):
    s=game(cards)
    empty_hands(s,'p1','p2','p3')
    source=cast(s,'Enemy of Enlightenment')
    to_phase(s,'main1',2)
    empty_hands(s,'p2','p3')
    for name in ['Faithless Looting','Grizzly Bears','Llanowar Elves','Serra Angel']:
        put(s,name,'hand','p2')
    assert ch(s,source).pt==(1,1)
    cast(s,'Faithless Looting','p2')
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='discard' and d.player=='p2'
    assert ch(s,source).pt==(0,0) and s.state.cards[source.id].zone=='p1:battlefield'
    act(s,'p2',type='choose',decision_id=d.id,option_ids=[o.id for o in d.options[:2]])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:battlefield' and ch(s,source).pt==(2,2)
    roundtrip(s)


def run_cold(s,tmp_path,mode,meta):
    import os
    import subprocess
    import sys

    import app

    meta={**meta,'mode':mode}
    saved=tmp_path/f'counts94-{mode}.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_designations import roundtrip
from tests.test_rules_static_counts94 import cast,choose_type
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
m=json.loads(sys.argv[3])
def ch(cid):return Plan.view(s.state,'p1',repo).ch(s.state.cards[cid])
if m['mode']=='cap':
 assert ch(m['bear']).pt==(13,13)
 human=cast(s,'Arcane Adaptation');choose_type(s,'Human')
 assert ch(m['bear']).pt==(3,3)
 cast(s,'Disenchant',targets=[human.id])
 assert ch(m['bear']).pt==(13,13)
elif m['mode']=='light':
 assert ch(m['bear']).pt==(4,4) and ch(m['hybrid']).pt==(13,13)
 cast(s,'Mirrorweave',targets=[m['hybrid']])
 assert ch(m['bear']).pt==(15,15)
 to_phase(s,'main1',2)
 assert ch(m['bear']).pt==(4,4)
elif m['mode']=='cda':
 assert ch(m['source']).pt==(2,2)
 source=cast(s,'Umbra Stalker')
 assert ch(source.id).pt==(2,2)
 crypt=cast(s,"Tormod's Crypt");wait_priority(s,'p1')
 act(s,'p1',type='activate_ability',card_id=crypt.id,ability=0,targets=['p1'],sources=[]);settle(s)
 assert s.state.cards[source.id].zone=='p1:graveyard' and ch(source.id).pt==(3,3)
else:
 base=int(repo.resolve('Dark Matter Manipulator')['power'])
 assert len(s.state.zones['p1:graveyard'])==7 and ch(m['source']).pt[0]==base+2
 cid=s.state.zones['p1:graveyard'][0]
 act(s,'p1',type='move',card_ids=[cid],to={'player':'p1','zone':'library'})
 assert ch(m['source']).pt[0]==base
 cast(s,'Reach Through Mists')
 assert ch(m['source']).pt[0]==base+2
 act(s,'p1',type='set_controller',card_ids=[m['source']],player='p2')
 assert ch(m['source']).pt[0]==base
roundtrip(s);repo.close()
'''
    backend=Path(app.__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(s.cards.db_path),json.dumps(meta)],cwd=backend,
                          env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('mode',['light','cda','floor'])
def test_true_cold_numeric_statics(cards,tmp_path,mode):
    s=game(cards)
    if mode=='light':
        bear=put(s,'Grizzly Bears','battlefield')
        hybrid=put(s,'Divinity of Pride','battlefield')
        act(s,'p1',type='counter',card_ids=[bear.id],kind='+1/+1',delta=2)
        cast(s,'Light from Within')
        meta={'bear':bear.id,'hybrid':hybrid.id}
    elif mode=='cda':
        put(s,'Dismember','graveyard')
        source=put(s,'Umbra Stalker','hand')
        meta={'source':source.id}
    else:
        for name in ['Divinity of Pride','Serra Angel','Eight-and-a-Half-Tails','Reaper King']:
            put(s,name,'graveyard')
        put(s,'Reach Through Mists','hand')
        source=cast(s,'Dark Matter Manipulator')
        meta={'source':source.id}
    run_cold(s,tmp_path,mode,meta)
