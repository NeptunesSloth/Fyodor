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

NAMES=['Rusted Relic','Futurist Operative','Grand Master of Flowers']
DATA = json.loads((Path(__file__).parent/'fixtures/conditional_animation92_cards.json').read_text())
ALL = [c['name'] for c in DATA]


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
    source=put(s,name,'hand',pid)
    mana(s,pid,C=20,W=10,U=10,B=10,R=10,G=10)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=list(targets),sources=[],**kwargs)
    settle(s)
    return source


def ch(s,source):
    return Plan.view(s.state,'p1',s.cards).ch(s.state.cards[source.id])


@pytest.mark.parametrize('name',NAMES)
def test_native_full_whole_cast(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'
    s=game(cards)
    source=cast(s,name)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)


def test_native_relic_threshold_current_control_and_actual_disruption(cards):
    s=game(cards)
    relic=cast(s,'Rusted Relic')
    assert not ch(s,relic).is_creature
    first=cast(s,'Ornithopter')
    assert not ch(s,relic).is_creature
    second=cast(s,'Darksteel Relic')
    assert ch(s,relic).is_creature and ch(s,relic).pt==(5,5) and 'Golem' in ch(s,relic).subtypes
    act(s,'p1',type='set_controller',card_ids=[second.id],player='p2')
    assert not ch(s,relic).is_creature
    act(s,'p2',type='set_controller',card_ids=[second.id],player='p1')
    assert ch(s,relic).is_creature
    cast(s,'Disenchant',targets=[first.id])
    assert not ch(s,relic).is_creature
    roundtrip(s)


def test_native_operative_types_counter_and_actual_untap(cards):
    s=game(cards)
    source=cast(s,'Futurist Operative')
    assert ch(s,source).pt==(3,4) and 'Ninja' in ch(s,source).subtypes
    act(s,'p1',type='counter',card_ids=[source.id],kind='+1/+1',delta=1)
    act(s,'p1',type='tap',card_ids=[source.id])
    assert ch(s,source).pt==(2,2) and ch(s,source).subtypes==frozenset({'Human','Citizen'})
    assert 'cant_be_blocked' in ch(s,source).imposed
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,sources=[])
    settle(s)
    assert not s.state.cards[source.id].tapped and ch(s,source).pt==(4,5) and 'Ninja' in ch(s,source).subtypes
    assert 'cant_be_blocked' not in ch(s,source).imposed
    roundtrip(s)


def test_native_master_seven_type_keywords_damage_and_reversion(cards):
    s=game(cards)
    source=cast(s,'Grand Master of Flowers')
    assert 'Planeswalker' in ch(s,source).types and not ch(s,source).is_creature
    act(s,'p1',type='counter',card_ids=[source.id],kind='loyalty',delta=4)
    assert ch(s,source).types==frozenset({'Creature'}) and ch(s,source).pt==(7,7)
    assert ch(s,source).subtypes==frozenset({'Dragon','God'})
    assert {'flying','indestructible'}<=ch(s,source).keywords
    cast(s,'Shock',targets=[source.id])
    assert s.state.cards[source.id].counters['loyalty']==7 and s.state.cards[source.id].damage==2
    act(s,'p1',type='counter',card_ids=[source.id],kind='loyalty',delta=-1)
    assert 'Planeswalker' in ch(s,source).types and not ch(s,source).is_creature
    assert not {'flying','indestructible'}&ch(s,source).keywords
    roundtrip(s)


def test_native_operative_timestamp_is_entry_not_tapping(cards):
    s=game(cards)
    source=cast(s,'Futurist Operative')
    cast(s,'Diminish',targets=[source.id])
    cast(s,'Giant Growth',targets=[source.id])
    act(s,'p1',type='counter',card_ids=[source.id],kind='+1/+1',delta=1)
    act(s,'p1',type='tap',card_ids=[source.id])
    assert ch(s,source).pt==(5,5)
    to_phase(s,'main1',2)
    assert ch(s,source).pt==(2,2)
    roundtrip(s)


def test_native_operative_forbidden_block_then_untap_still_attacking(cards):
    from app.game.errors import ActionError

    s=game(cards)
    source=cast(s,'Futurist Operative')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    to_phase(s,'declare_attackers',4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    assert ch(s,source).pt==(1,1)
    to_phase(s,'declare_blockers',4)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':bear.id,'attacker_id':source.id}])
    assert s.state.model_dump_json()==before
    act(s,'p2',type='declare_blockers',blocks=[])
    mana(s,'p1',U=3,C=4)
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,sources=[])
    settle(s)
    assert s.state.cards[source.id].attacking is not None and ch(s,source).pt==(3,4)
    to_phase(s,'main2',4)
    assert s.state.players['p2'].life==37
    roundtrip(s)


def test_native_relic_loss_of_animation_removes_combat(cards):
    s=game(cards)
    source=cast(s,'Rusted Relic')
    cast(s,'Ornithopter')
    support=cast(s,'Darksteel Relic')
    to_phase(s,'declare_attackers',4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    act(s,'p1',type='set_controller',card_ids=[support.id],player='p2')
    act(s,s.state.rules.priority,type='pass_priority')
    assert not ch(s,source).is_creature and s.state.cards[source.id].attacking is None
    act(s,'p2',type='set_controller',card_ids=[support.id],player='p1')
    assert ch(s,source).is_creature and s.state.cards[source.id].attacking is None
    to_phase(s,'main2',4)
    assert s.state.players['p2'].life==40
    roundtrip(s)


@pytest.mark.parametrize('name',['Youthful Knight','Fencing Ace','Steadfast Guard'])
def test_native_master_excluded_keywords_rejected_atomically(cards,name):
    from app.game.errors import ActionError

    s=game(cards)
    source=cast(s,'Grand Master of Flowers')
    target=put(s,name,'battlefield','p2')
    wait_priority(s,'p1')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=1,targets=[target.id],sources=[])
    assert s.state.model_dump_json()==before


def test_native_master_plus_one_seven_before_response_and_duration(cards):
    s=game(cards)
    source=cast(s,'Grand Master of Flowers')
    target=put(s,'Grizzly Bears','battlefield','p2')
    act(s,'p1',type='counter',card_ids=[source.id],kind='loyalty',delta=3)
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,targets=[target.id],sources=[])
    assert ch(s,source).types==frozenset({'Creature'}) and ch(s,source).pt==(7,7)
    settle(s)
    assert 'cant_attack_or_block' in ch(s,target).imposed
    to_phase(s,'main1',2)
    assert 'cant_attack_or_block' in ch(s,target).imposed
    to_phase(s,'main1',4)
    assert 'cant_attack_or_block' not in ch(s,target).imposed
    roundtrip(s)


@pytest.mark.parametrize('mode',['relic','operative','master'])
def test_true_cold_animation_predicates(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    import app

    s=game(cards)
    relic=cast(s,'Rusted Relic')
    cast(s,'Ornithopter')
    support=cast(s,'Darksteel Relic')
    operative=cast(s,'Futurist Operative')
    master=cast(s,'Grand Master of Flowers')
    act(s,'p1',type='tap',card_ids=[operative.id])
    act(s,'p1',type='counter',card_ids=[master.id],kind='loyalty',delta=4)
    saved=tmp_path/'animation92.json'
    saved.write_text(s.state.model_dump_json())
    meta={'mode':mode,'relic':relic.id,'support':support.id,'operative':operative.id,'master':master.id}
    code=r'''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana,wait_priority
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
m=json.loads(sys.argv[3])
def ch(key):return Plan.view(s.state,'p1',repo).ch(s.state.cards[m[key]])
assert ch('relic').is_creature and ch('relic').pt==(5,5)
assert ch('operative').pt==(1,1) and ch('operative').subtypes==frozenset({'Human','Citizen'})
assert ch('master').types==frozenset({'Creature'}) and {'flying','indestructible'}<=ch('master').keywords
if m['mode']=='relic':
 act(s,'p1',type='set_controller',card_ids=[m['support']],player='p2')
 assert not ch('relic').is_creature
elif m['mode']=='operative':
 mana(s,'p1',U=3,C=4);wait_priority(s,'p1')
 act(s,'p1',type='activate_ability',card_id=m['operative'],ability=1,sources=[]);settle(s)
 assert ch('operative').pt==(3,4) and 'Ninja' in ch('operative').subtypes
else:
 act(s,'p1',type='counter',card_ids=[m['master']],kind='loyalty',delta=-1)
 assert 'Planeswalker' in ch('master').types and not ch('master').is_creature
roundtrip(s);repo.close()
'''
    backend=Path(app.__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),json.dumps(meta)],cwd=backend,
                          env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr


def test_native_relic_actual_spell_type_loss_removes_combat(cards):
    s=game(cards)
    source=cast(s,'Rusted Relic')
    support=cast(s,'Ornithopter')
    cast(s,'Darksteel Relic')
    to_phase(s,'declare_attackers',4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    cast(s,'Disenchant',targets=[support.id])
    assert not ch(s,source).is_creature and s.state.cards[source.id].attacking is None


def test_native_master_proliferate_while_attacked_removes_target_before_blocks(cards):
    s=game(cards)
    to_phase(s,'main1',2)
    master=cast(s,'Grand Master of Flowers','p2')
    attacker=put(s,'Grizzly Bears','battlefield')
    act(s,'p2',type='counter',card_ids=[master.id],kind='loyalty',delta=3)
    to_phase(s,'declare_attackers',4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':master.id}])
    cast(s,'Steady Progress','p2')
    decision=s.state.rules.decision
    assert decision is not None and decision.resume['step']=='proliferate'
    option=next(o.id for o in decision.options if o.id==master.id)
    act(s,'p2',type='choose',decision_id=decision.id,option_ids=[option])
    settle(s)
    assert ch(s,master).types==frozenset({'Creature'}) and s.state.cards[master.id].counters['loyalty']==7
    assert s.state.cards[attacker.id].attacking is None and s.state.cards[attacker.id].is_attacking
    assert s.state.cards[attacker.id].attacking_without_target=='p2'
    to_phase(s,'declare_blockers',4)
    act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':master.id,'attacker_id':attacker.id}])
    to_phase(s,'main2',4)
    assert s.state.cards[attacker.id].zone=='p1:graveyard'
    assert s.state.cards[master.id].zone=='p2:battlefield' and s.state.cards[master.id].counters['loyalty']==7
    roundtrip(s)


@pytest.mark.parametrize('present',[False,True])
def test_native_master_search_graveyard_present_or_absent(cards,present):
    s=game(cards)
    master=cast(s,'Grand Master of Flowers')
    monk=put(s,'Monk of the Open Hand','graveyard' if present else 'exile')
    library=list(s.state.zones['p1:library'])
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=master.id,ability=2,sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='search_zones'
    act(s,'p1',type='choose',decision_id=d.id,option_ids=['graveyard'])
    settle(s)
    d=s.state.rules.decision
    if d is not None:
        assert d.resume['step']=='search'
        act(s,'p1',type='choose',decision_id=d.id,option_ids=[monk.id] if present else [])
        settle(s)
    assert s.state.cards[monk.id].zone==('p1:hand' if present else 'p1:exile')
    assert list(s.state.zones['p1:library'])==library
    assert s.state.cards[master.id].counters['loyalty']==4
    roundtrip(s)
