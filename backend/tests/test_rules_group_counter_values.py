"""Canonical grouped counter instructions freeze current recipients and quantities."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Sovereign Okinec Ahau','Phyresis Outbreak','Vraska, Regal Gorgon','Aku Djinn','Parallax Inhibitor','Zar Ojanen, Scion of Efrava']
EXTRA=['Grizzly Bears','Shalai, Voice of Plenty','Giant Growth','Turn to Frog','Doubling Season','Hardened Scales','Vorinclex, Monstrous Raider','Solemnity','Forest','Island','Swamp','Mountain','Plains','Tangle Wire','Blastoderm','Chronozoa','Humility','Char-Rumbler','Prismatic Omen']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/group_counter_values_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='gcv',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    ns=[*NAMES,*EXTRA]
    return table(cards,ns,ns,ns)


def cast(s,name,targets=()):
    c=put(s,name,'hand')
    pay(s,'p1',name)
    act(s,'p1',type='cast_spell',card_id=c.id,sources=[],targets=[x['card_id'] if isinstance(x,dict) else x for x in targets])
    settle(s)
    return c


def ch(s,c):
    return Plan(s.state,'p1',s.cards,None).ch(s.state.cards[c.id])


def count(s,c):
    return s.state.cards[c.id].counters.get('+1/+1',0)


def attack(s,source):
    # The source has been under its controller's control since before this turn.
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_sovereign_each_current_difference_ignores_unchanged_and_opponents(cards):
    s=game(cards)
    source=put(s,NAMES[0],'battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    other=put(s,'Shalai, Voice of Plenty','battlefield')
    enemy=put(s,'Grizzly Bears','battlefield','p2')
    act(s,'p1',type='set_counter',card_id=source.id,kind='+1/+1',value=1)
    act(s,'p1',type='set_counter',card_id=bear.id,kind='+1/+1',value=2)
    act(s,'p2',type='set_counter',card_id=enemy.id,kind='+1/+1',value=3)
    attack(s,source)
    assert count(s,source)==2 and count(s,bear)==4
    assert count(s,other)==0 and count(s,enemy)==3
    roundtrip(s)


def test_sovereign_current_pump_counts_but_base_setting_does_not(cards):
    s=game(cards)
    source=put(s,NAMES[0],'battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    to_phase(s,'main1',turn=4)
    cast(s,'Turn to Frog',[{'card_id':bear.id}])
    cast(s,'Giant Growth',[{'card_id':bear.id}])
    attack(s,source)
    assert count(s,bear)==3 and ch(s,bear).pt==(7,7)
    roundtrip(s)


@pytest.mark.parametrize('blocked',[False,True])
def test_sovereign_native_counter_replacement_and_prevention(cards,blocked):
    s=game(cards)
    source=put(s,NAMES[0],'battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    act(s,'p1',type='set_counter',card_id=bear.id,kind='+1/+1',value=2)
    put(s,'Solemnity' if blocked else 'Doubling Season','battlefield')
    attack(s,source)
    assert count(s,bear)==(2 if blocked else 6)
    roundtrip(s)


def test_outbreak_uses_each_current_controller_poison_and_native_eot(cards):
    s=game(cards)
    own=put(s,'Shalai, Voice of Plenty','battlefield')
    a=put(s,'Shalai, Voice of Plenty','battlefield','p2')
    b=put(s,'Shalai, Voice of Plenty','battlefield','p3')
    act(s,'p2',type='set_resource',key='poison',value=1)
    cast(s,NAMES[1])
    assert s.state.players['p2'].resources['poison']==2
    assert s.state.players['p3'].resources['poison']==1
    assert ch(s,own).pt==(3,4) and ch(s,a).pt==(1,2) and ch(s,b).pt==(2,3)
    act(s,'p2',type='set_resource',key='poison',value=5)
    assert ch(s,a).pt==(1,2)
    to_phase(s,'main1',turn=2)
    assert ch(s,a).pt==(3,4) and ch(s,b).pt==(3,4)
    roundtrip(s)


@pytest.mark.parametrize('block',[False,True])
def test_outbreak_counter_replacement_or_prevention_changes_following_pump(cards,block):
    s=game(cards)
    a=put(s,'Shalai, Voice of Plenty','battlefield','p2')
    put(s,'Solemnity' if block else 'Vorinclex, Monstrous Raider','battlefield')
    cast(s,NAMES[1])
    assert s.state.players['p2'].resources.get('poison',0)==(0 if block else 2)
    assert ch(s,a).pt==((3,4) if block else (1,2))
    roundtrip(s)


def test_vraska_loyalty_paid_and_graveyard_count_put_on_all_controlled_only(cards):
    s=game(cards)
    source=cast(s,NAMES[2])
    act(s,'p1',type='set_counter',card_id=source.id,kind='loyalty',value=10)
    bear=put(s,'Grizzly Bears','battlefield')
    enemy=put(s,'Grizzly Bears','battlefield','p2')
    put(s,'Aku Djinn','graveyard')
    put(s,'Zar Ojanen, Scion of Efrava','graveyard')
    put(s,'Forest','graveyard')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'For each creature card'),sources=[])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert count(s,bear)==2 and count(s,enemy)==0
    roundtrip(s)


def test_aku_real_upkeep_puts_on_every_opponents_creatures_not_own(cards):
    s=game(cards)
    source=put(s,'Aku Djinn','battlefield')
    a=put(s,'Grizzly Bears','battlefield','p2')
    b=put(s,'Shalai, Voice of Plenty','battlefield','p3')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert count(s,a)==1 and count(s,b)==1 and count(s,source)==0
    roundtrip(s)


def test_inhibitor_costs_and_current_fading_not_vanishing_or_opponent(cards):
    s=game(cards)
    source=put(s,'Parallax Inhibitor','battlefield')
    artifact=put(s,'Tangle Wire','battlefield')
    creature=put(s,'Blastoderm','battlefield')
    vanishing=put(s,'Chronozoa','battlefield')
    enemy=put(s,'Tangle Wire','battlefield','p2')
    act(s,'p1',type='add_mana',mana={'C':1})
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'Put a fade counter'),sources=[])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    settle(s)
    assert s.state.cards[artifact.id].counters.get('fade')==1
    assert s.state.cards[creature.id].counters.get('fade')==1
    assert not s.state.cards[vanishing.id].counters and not s.state.cards[enemy.id].counters
    roundtrip(s)


@pytest.mark.parametrize('lands,eligible',[(1,False),(2,False),(3,True),(5,True)])
def test_zar_strict_current_toughness_below_current_domain(cards,lands,eligible):
    s=game(cards)
    source=put(s,'Zar Ojanen, Scion of Efrava','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    enemy=put(s,'Grizzly Bears','battlefield','p2')
    for name in ['Forest','Island','Swamp','Mountain','Plains'][:lands]:
        put(s,name,'battlefield')
    attack(s,source)
    assert count(s,bear)==int(eligible) and count(s,enemy)==0
    assert count(s,source)==int(lands>4)
    roundtrip(s)


def test_inhibitor_uses_current_abilities_after_humility(cards):
    s=game(cards)
    source=put(s,'Parallax Inhibitor','battlefield')
    artifact=put(s,'Tangle Wire','battlefield')
    creature=put(s,'Blastoderm','battlefield')
    put(s,'Humility','battlefield')
    act(s,'p1',type='add_mana',mana={'C':1})
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'Put a fade counter'),sources=[])
    settle(s)
    assert s.state.cards[artifact.id].counters.get('fade')==1
    assert not s.state.cards[creature.id].counters
    roundtrip(s)


def test_outbreak_uses_resolution_controller_then_fixes_membership(cards):
    s=game(cards)
    a=put(s,'Shalai, Voice of Plenty','battlefield','p2')
    act(s,'p3',type='set_resource',key='poison',value=1)
    act(s,'p1',type='set_prefs',hold_priority=True)
    spell=put(s,'Phyresis Outbreak','hand')
    pay(s,'p1','Phyresis Outbreak')
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[],targets=[])
    act(s,'p1',type='set_controller',card_ids=[a.id],player='p3')
    settle(s)
    assert ch(s,a).pt==(1,2)
    act(s,'p1',type='set_controller',card_ids=[a.id],player='p1')
    assert ch(s,a).pt==(1,2)
    later=put(s,'Grizzly Bears','battlefield','p2')
    assert ch(s,later).pt==(2,2)
    roundtrip(s)


def test_zar_current_toughness_above_domain_excludes_pumped_creature(cards):
    s=game(cards)
    source=put(s,'Zar Ojanen, Scion of Efrava','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    for n in ['Forest','Island','Swamp']:
        put(s,n,'battlefield')
    to_phase(s,'main1',turn=4)
    cast(s,'Giant Growth',[{'card_id':bear.id}])
    attack(s,source)
    assert count(s,bear)==0
    roundtrip(s)


def test_sovereign_simultaneous_amounts_survive_replacement_choices_and_cold_load(cards,tmp_path):
    import subprocess
    import sys

    s=game(cards)
    source=put(s,'Sovereign Okinec Ahau','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    act(s,'p1',type='set_counter',card_id=source.id,kind='+1/+1',value=1)
    act(s,'p1',type='set_counter',card_id=bear.id,kind='+1/+1',value=2)
    put(s,'Doubling Season','battlefield')
    put(s,'Hardened Scales','battlefield')
    attack(s,source)
    d=s.state.rules.decision
    assert d and d.resume['step']=='replace_order'
    saved=tmp_path/'group-counters.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,db,source,bear=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
for _ in range(30):
 d=s.state.rules.decision
 if d is not None:
  assert d.resume['step']=='replace_order',d
  s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[d.options[0].id]})
 elif s.state.zones['stack']:
  s.perform(s.state.rules.priority,{'type':'pass_priority'})
 else:break
assert s.state.cards[source].counters['+1/+1'] in (4,5)
assert s.state.cards[bear].counters['+1/+1'] in (7,8)
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id,bear.id],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_sovereign_negative_base_power_difference_is_not_clamped_early(cards):
    s=game(cards)
    source=put(s,'Sovereign Okinec Ahau','battlefield')
    creature=put(s,'Char-Rumbler','battlefield')
    to_phase(s,'main1',turn=4)
    cast(s,'Giant Growth',[creature.id])
    assert ch(s,creature).pt[0]==2 and ch(s,creature).base_pt[0]==-1
    attack(s,source)
    assert count(s,creature)==3
    roundtrip(s)


def test_zar_uses_current_derived_land_types_not_number_of_lands(cards):
    s=game(cards)
    source=put(s,'Zar Ojanen, Scion of Efrava','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    put(s,'Forest','battlefield')
    put(s,'Prismatic Omen','battlefield')
    attack(s,source)
    assert count(s,bear)==1 and count(s,source)==1
    roundtrip(s)
