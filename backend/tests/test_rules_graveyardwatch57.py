"""Native graveyard return watchers preserve actual events and original object identities."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Sword of the Meek','Skyfire Phoenix',"Chandra's Phoenix",'Deathmist Raptor','Command the Stage','Grave Scrabbler','Dawn Evangel']


@pytest.fixture
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/graveyardwatch57_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='oc55',number=str(i),**{k:v for k,v in c.items() if k not in ('name','set_code')})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names=[*NAMES,'Grizzly Bears','Llanowar Elves','Sol Ring','Pacifism','Lightning Bolt','Forest','Island','Counterspell','Chandra Nalaar','Tormenting Voice','Glorious Anthem','Gravel Slinger','Doubling Season','Wrath of God',"Praetor's Grasp",'Clever Concealment']
    s=table(cards,names,names,names)
    to_phase(s,'main1',1)
    act(s,'p1',type='add_mana',player='p1',mana={'G':20,'W':20,'R':20,'U':20,'B':20,'C':20})
    return s


def cast(s,name,*,targets=None,face_down=False,target_counts=None):
    source=put(s,name,'hand')
    act(s,'p1',type='cast_spell',card_id=source.id,targets=targets or [],face_down=face_down,sources=[],**({'target_counts':target_counts} if target_counts is not None else {}))
    settle(s)
    return source


def answer(s,ids):
    d=s.state.rules.decision
    assert d is not None
    act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
    settle(s)


def test_sword_actual_entry_returns_and_equips_new_object(cards):
    s=setup(cards)
    sword=put(s,'Sword of the Meek','graveyard')
    elf=cast(s,'Llanowar Elves')
    assert s.state.rules.decision is not None
    answer(s,['yes'])
    assert sword.zone=='p1:battlefield' and sword.attached_to==elf.id
    assert Plan(s.state,'p1',cards,None).ch(elf).pt==(2,3)
    roundtrip(s)


def test_sword_actual_continuous_entry_stats_prevent_trigger(cards):
    s=setup(cards)
    sword=put(s,'Sword of the Meek','graveyard')
    cast(s,'Glorious Anthem')
    elf=cast(s,'Llanowar Elves')
    assert Plan(s.state,'p1',cards,None).ch(elf).pt==(2,2)
    assert sword.zone=='p1:graveyard' and s.state.rules.decision is None
    roundtrip(s)


def test_skyfire_actual_commander_cast_returns_before_commander(cards):
    s=setup(cards)
    source=put(s,'Skyfire Phoenix','graveyard')
    commander=next(c for c in s.state.cards.values() if c.owner=='p1' and c.zone=='p1:command')
    act(s,'p1',type='cast_spell',card_id=commander.id,sources=[])
    for _ in range(20):
        if source.zone=='p1:battlefield':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert source.zone=='p1:battlefield' and commander.zone=='stack'
    settle(s)
    assert commander.zone=='p1:battlefield'
    roundtrip(s)


def test_chandra_phoenix_actual_red_spell_damage_returns(cards):
    s=setup(cards)
    source=put(s,"Chandra's Phoenix",'graveyard')
    cast(s,'Lightning Bolt',targets=['p2'])
    assert source.zone=='p1:hand' and s.state.players['p2'].life==37
    roundtrip(s)


def test_chandra_phoenix_actual_red_planeswalker_damage_returns(cards):
    s=setup(cards)
    source=put(s,"Chandra's Phoenix",'graveyard')
    chandra=cast(s,'Chandra Nalaar')
    act(s,'p1',type='activate_ability',card_id=chandra.id,ability=0,targets=['p2'],sources=[])
    settle(s)
    assert source.zone=='p1:hand' and s.state.players['p2'].life==39
    roundtrip(s)


@pytest.mark.parametrize('face_down',[False,True])
def test_deathmist_native_morph_turns_up_then_return_face_choice(cards,face_down):
    s=setup(cards)
    source=put(s,'Deathmist Raptor','graveyard')
    cast(s,'Gravel Slinger',face_down=True)
    slinger=next(c for c in s.state.cards.values() if c.name=='Gravel Slinger' and c.owner=='p1')
    act(s,'p1',type='turn_face_up',card_id=slinger.id)
    settle(s)
    answer(s,['yes'])
    d=s.state.rules.decision
    assert d is not None
    answer(s,['1' if face_down else '0'])
    source=next(c for c in s.state.cards.values() if c.name=='Deathmist Raptor' and c.owner=='p1')
    assert source.zone=='p1:battlefield' and source.face_down==face_down
    if face_down:
        assert Plan(s.state,'p1',cards,None).ch(source).pt==(2,2)
    roundtrip(s)


def test_command_actual_cadet_excludes_all_new_tokens_from_counter_batch(cards):
    s=setup(cards)
    first=cast(s,'Command the Stage')
    original=next(c for c in s.state.cards.values() if c.is_token and c.name=='Cadet' and c.owner=='p1')
    assert not original.counters
    act(s,'p1',type='move',card_ids=[first.id],to={'player':'p1','zone':'hand'})
    cast(s,'Doubling Season')
    cast(s,'Command the Stage')
    tokens=[c for c in s.state.cards.values() if c.is_token and c.name=='Cadet' and c.owner=='p1']
    assert len(tokens)==3 and original.counters=={'+1/+1':2}
    assert all(not c.counters for c in tokens if c.id!=original.id)
    roundtrip(s)


@pytest.mark.parametrize('madness',[False,True])
def test_scrabbler_actual_madness_payment_controls_etb(cards,madness):
    s=setup(cards)
    target=put(s,'Grizzly Bears','graveyard')
    source=put(s,'Grave Scrabbler','hand')
    if madness:
        voice=put(s,'Tormenting Voice','hand')
        act(s,'p1',type='cast_spell',card_id=voice.id,sources=[],cost_choices=[{'component':0,'cards':[source.id]}])
        settle(s)
        assert s.state.rules.decision is not None and 'Madness' in s.state.rules.decision.prompt
        answer(s,['yes'])
        d=s.state.rules.decision
        assert d is not None
        answer(s,[target.id])
        answer(s,['yes'])
        assert target.zone=='p1:hand'
    else:
        cast(s,'Grave Scrabbler')
        assert target.zone=='p1:graveyard' and s.state.rules.decision is None
    assert source.zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('target_player',['p1','p2'])
def test_command_actual_last_turn_noncombat_damage_history(cards,target_player):
    s=setup(cards)
    source=cast(s,'Command the Stage')
    cast(s,'Lightning Bolt',targets=[target_player])
    to_phase(s,'upkeep',2)
    settle(s)
    assert source.zone==('p1:hand' if target_player=='p2' else 'p1:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('host_owner',['p1','p2'])
def test_dawn_actual_your_aura_on_any_dying_creature(cards,host_owner):
    s=setup(cards)
    cast(s,'Dawn Evangel')
    returned=put(s,'Llanowar Elves','graveyard')
    host=put(s,'Grizzly Bears','battlefield',host_owner)
    cast(s,'Pacifism',targets=[host.id])
    cast(s,'Lightning Bolt',targets=[host.id])
    d=s.state.rules.decision
    assert d is not None and returned.id in [o.id for o in d.options]
    answer(s,[returned.id])
    assert returned.zone=='p1:hand' and host.zone==host_owner+':graveyard'
    roundtrip(s)


def test_dawn_foreign_controlled_aura_does_not_trigger(cards):
    s=setup(cards)
    cast(s,'Dawn Evangel')
    returned=put(s,'Llanowar Elves','graveyard')
    host=put(s,'Grizzly Bears','battlefield')
    aura=cast(s,'Pacifism',targets=[host.id])
    act(s,'p1',type='set_controller',card_ids=[aura.id],player='p2')
    cast(s,'Lightning Bolt',targets=[host.id])
    assert returned.zone=='p1:graveyard' and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('self_host',[False,True])
def test_dawn_actual_source_death_or_simultaneous_sweeper_looks_back(cards,self_host):
    s=setup(cards)
    source=cast(s,'Dawn Evangel')
    returned=put(s,'Llanowar Elves','graveyard')
    host=source if self_host else put(s,'Grizzly Bears','battlefield')
    cast(s,'Pacifism',targets=[host.id])
    cast(s,'Lightning Bolt',targets=[host.id]) if self_host else cast(s,'Wrath of God')
    assert source.zone=='p1:graveyard'
    d=s.state.rules.decision
    assert d is not None and returned.id in [o.id for o in d.options]
    answer(s,[returned.id])
    assert returned.zone=='p1:hand'
    roundtrip(s)


def test_sword_event_creature_gone_returns_unattached(cards):
    s=setup(cards)
    source=put(s,'Sword of the Meek','graveyard')
    elf=cast(s,'Llanowar Elves')
    act(s,'p1',type='move',card_ids=[elf.id],to={'player':'p1','zone':'exile'})
    answer(s,['yes'])
    assert source.zone=='p1:battlefield' and not source.attached_to
    roundtrip(s)


def test_sword_changed_event_stats_do_not_recheck_1_1(cards):
    s=setup(cards)
    source=put(s,'Sword of the Meek','graveyard')
    elf=cast(s,'Llanowar Elves')
    act(s,'p1',type='counter',card_ids=[elf.id],kind='+1/+1',delta=3)
    answer(s,['yes'])
    assert source.zone=='p1:battlefield' and source.attached_to==elf.id
    assert Plan(s.state,'p1',cards,None).ch(elf).pt==(5,6)
    roundtrip(s)


def test_sword_original_source_graveyard_incarnation_only(cards):
    s=setup(cards)
    source=put(s,'Sword of the Meek','graveyard')
    elf=cast(s,'Llanowar Elves')
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'exile'})
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    answer(s,['yes'])
    assert source.zone=='p1:graveyard' and not source.attached_to
    assert Plan(s.state,'p1',cards,None).ch(elf).pt==(1,1)
    roundtrip(s)


@pytest.mark.parametrize('name',['Sword of the Meek','Deathmist Raptor'])
def test_optional_graveyard_return_decline_leaves_source(cards,name):
    s=setup(cards)
    source=put(s,name,'graveyard')
    if name=='Sword of the Meek':
        cast(s,'Llanowar Elves')
    else:
        cast(s,'Gravel Slinger',face_down=True)
        slinger=next(c for c in s.state.cards.values() if c.name=='Gravel Slinger' and c.owner=='p1')
        act(s,'p1',type='turn_face_up',card_id=slinger.id)
        settle(s)
    answer(s,['no'])
    assert source.zone=='p1:graveyard' and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('recipient',['p1','creature'])
def test_chandra_red_damage_not_to_opponent_player_does_not_return(cards,recipient):
    s=setup(cards)
    source=put(s,"Chandra's Phoenix",'graveyard')
    elf=put(s,'Llanowar Elves','battlefield')
    cast(s,'Lightning Bolt',targets=['p1' if recipient=='p1' else elf.id])
    assert source.zone=='p1:graveyard' and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_cold_native_watchers_without_adapters(cards,tmp_path,name):
    import subprocess
    import sys

    s=setup(cards)
    target=None
    if name=='Sword of the Meek':
        source=put(s,name,'graveyard')
        target=cast(s,'Llanowar Elves')
    elif name=='Skyfire Phoenix':
        source=put(s,name,'graveyard')
        commander=next(c for c in s.state.cards.values() if c.owner=='p1' and c.zone=='p1:command')
        act(s,'p1',type='cast_spell',card_id=commander.id,sources=[])
    elif name=="Chandra's Phoenix":
        source=put(s,name,'graveyard')
        bolt=put(s,'Lightning Bolt','hand')
        act(s,'p1',type='cast_spell',card_id=bolt.id,targets=['p2'],sources=[])
    elif name=='Deathmist Raptor':
        source=put(s,name,'graveyard')
        cast(s,'Gravel Slinger',face_down=True)
        slinger=next(c for c in s.state.cards.values() if c.name=='Gravel Slinger' and c.owner=='p1')
        act(s,'p1',type='turn_face_up',card_id=slinger.id)
        settle(s)
        answer(s,['yes'])
    elif name=='Command the Stage':
        source=cast(s,name)
        cast(s,'Lightning Bolt',targets=['p2'])
    elif name=='Grave Scrabbler':
        target=put(s,'Grizzly Bears','graveyard')
        source=put(s,name,'hand')
        voice=put(s,'Tormenting Voice','hand')
        act(s,'p1',type='cast_spell',card_id=voice.id,sources=[],cost_choices=[{'component':0,'cards':[source.id]}])
        settle(s)
        answer(s,['yes'])
    else:
        source=cast(s,name)
        target=put(s,'Llanowar Elves','graveyard')
        host=put(s,'Grizzly Bears','battlefield')
        cast(s,'Pacifism',targets=[host.id])
        bolt=put(s,'Lightning Bolt','hand')
        act(s,'p1',type='cast_spell',card_id=bolt.id,targets=[host.id],sources=[])
    saved=tmp_path/'watcher.json'
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
from tests.test_rules_wave30m_durations import to_phase
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
name,source,target=sys.argv[3:6]
def answer(ids):
 d=s.state.rules.decision
 assert d is not None
 act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
 settle(s)
if name=='Sword of the Meek':
 answer(['yes'])
 assert s.state.cards[source].zone=='p1:battlefield' and s.state.cards[source].attached_to==target
elif name=='Deathmist Raptor':
 answer(['1'])
 returned=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name==name)
 assert returned.zone=='p1:battlefield' and returned.face_down
elif name=='Command the Stage':
 to_phase(s,'upkeep',2)
 settle(s)
 assert s.state.cards[source].zone=='p1:hand'
elif name=='Grave Scrabbler':
 answer([target])
 answer(['yes'])
 assert s.state.cards[source].zone=='p1:battlefield' and s.state.cards[target].zone=='p1:hand'
elif name=='Dawn Evangel':
 settle(s)
 answer([target])
 assert s.state.cards[target].zone=='p1:hand'
else:
 settle(s)
 assert s.state.cards[source].zone==('p1:hand' if name=="Chandra's Phoenix" else 'p1:battlefield')
roundtrip(s)
repo.close()
"""
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),name,source.id,target.id if target else ''],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=90,check=False)
    assert result.returncode==0,result.stdout+result.stderr


def test_skyfire_actual_praetors_grasp_cast_opponents_commander_is_not_your_commander(cards):
    s=setup(cards)
    source=put(s,'Skyfire Phoenix','graveyard')
    foreign=next(c for c in s.state.cards.values() if c.owner=='p2' and c.zone=='p2:command')
    act(s,'p1',type='move',card_ids=[foreign.id],to={'player':'p2','zone':'library'},position='top')
    cast(s,"Praetor's Grasp",targets=['p2'])
    d=s.state.rules.decision
    assert d is not None and foreign.id in [o.id for o in d.options]
    answer(s,[foreign.id])
    if s.state.rules.decision is not None:
        answer(s,['no'])
    assert foreign.zone=='p2:exile'
    act(s,'p1',type='cast_spell',card_id=foreign.id,sources=[])
    settle(s)
    assert foreign.zone=='p1:battlefield' and source.zone=='p1:graveyard'
    roundtrip(s)


def test_dawn_independently_phased_out_aura_does_not_qualify(cards):
    s=setup(cards)
    cast(s,'Dawn Evangel')
    returned=put(s,'Llanowar Elves','graveyard')
    host=put(s,'Grizzly Bears','battlefield')
    aura=cast(s,'Pacifism',targets=[host.id])
    cast(s,'Clever Concealment',targets=[aura.id],target_counts=[1])
    assert aura.zone=='p1:phased' and aura.attached_to==host.id and host.zone=='p1:battlefield'
    cast(s,'Lightning Bolt',targets=[host.id])
    assert returned.zone=='p1:graveyard' and s.state.rules.decision is None
    roundtrip(s)
