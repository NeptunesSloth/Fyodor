"""Native graveyard either-watchers preserve commander ownership and Eerie return timing."""
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
from tests.test_rules_conditional_prevention import attack, damage
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Endless Ranks of HYDRA','Fear of Infinity',"Vivi's Persistence"]
PAYERS=[NAMES[0],NAMES[2]]


@pytest.fixture
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/graveyardwatch57_expanded3_cards.json').read_text())):
        if c.get('card_faces'):
            c={**c,'card_faces':[{'object':'card_face',**f} for f in c['card_faces']]}
        base[c['name']]=card(c['name'],set_code='oc55',number=str(i),**{k:v for k,v in c.items() if k not in ('name','set_code')})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names=[*NAMES,'Reanimate','Control Magic','Restricted Office // Lecture Hall','Grizzly Bears','Llanowar Elves','Pacifism','Lightning Bolt','Sol Ring','Forest']
    s=table(cards,names,names,names)
    to_phase(s,'main1',1)
    mana(s,'p1')
    return s


def mana(s,pid):
    act(s,pid,type='add_mana',player=pid,mana={k:20 for k in ['G','W','R','U','B','C']})


def cast(s,name,targets=None,pid='p1'):
    source=put(s,name,'hand',pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=targets or [],sources=[])
    settle(s)
    return source


def answer(s,ids):
    d=s.state.rules.decision
    assert d is not None
    act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
    settle(s)


def reanimated_commander(s,name,owned):
    owner='p1' if owned else 'p2'
    controller='p2' if owned else 'p1'
    commander=next(c for c in s.state.cards.values() if c.owner==owner and c.zone==owner+':command')
    act(s,'p1',type='move',card_ids=[commander.id],to={'player':owner,'zone':'graveyard'})
    if s.state.rules.decision is not None:
        answer(s,['no'])
    source=cast(s,name)
    while s.state.rules.decision is not None and s.state.rules.decision.resume.get('step')=='commander_zone':
        answer(s,['no'])
    assert commander.zone==owner+':graveyard' and source.zone=='p1:graveyard'
    if controller=='p2':
        to_phase(s,'main1',2)
    mana(s,'p1')
    mana(s,controller)
    cast(s,'Reanimate',targets=[commander.id],pid=controller)
    while s.state.rules.decision is not None and s.state.rules.decision.resume.get('step')=='commander_zone':
        answer(s,['no'])
    assert commander.owner==owner and commander.controller==controller and commander.zone==controller+':battlefield'
    return source,commander


@pytest.mark.parametrize('name',PAYERS)
@pytest.mark.parametrize('owned',[False,True])
def test_actual_reanimate_commander_entry_uses_owner_not_controller(cards,name,owned):
    s=setup(cards)
    source,_commander=reanimated_commander(s,name,owned)
    if owned:
        d=s.state.rules.decision
        assert d is not None and d.player=='p1' and d.resume.get('opt')
        answer(s,['pay'])
        assert source.zone=='p1:hand'
    else:
        assert s.state.rules.decision is None and source.zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name',PAYERS)
@pytest.mark.parametrize('owned',[False,True])
def test_actual_owned_or_stolen_commander_attack_uses_owner(cards,name,owned):
    s=setup(cards)
    source,commander=reanimated_commander(s,name,owned)
    if owned:
        answer(s,['decline'])
    actor='p2' if owned else 'p1'
    to_phase(s,'declare_attackers',5 if owned else 4)
    mana(s,'p1')
    act(s,actor,type='declare_attackers',attackers=[{'card_id':commander.id,'target':'p3'}])
    settle(s)
    if owned:
        d=s.state.rules.decision
        assert d is not None and d.player=='p1' and d.resume.get('opt')
        answer(s,['pay'])
        assert source.zone=='p1:hand'
    else:
        assert s.state.rules.decision is None and source.zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name',PAYERS)
def test_optional_mana_decline_does_not_return(cards,name):
    s=setup(cards)
    source,_commander=reanimated_commander(s,name,True)
    answer(s,['decline'])
    assert source.zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name',PAYERS)
def test_return_cannot_follow_new_graveyard_source_incarnation(cards,name):
    s=setup(cards)
    source,_commander=reanimated_commander(s,name,True)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'exile'})
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    answer(s,['pay'])
    assert source.zone=='p1:graveyard'
    roundtrip(s)


def test_hydra_actual_cast_creates_one_menace_villain_per_opponent(cards):
    s=setup(cards)
    cast(s,'Endless Ranks of HYDRA')
    tokens=[c for c in s.state.cards.values() if c.is_token and c.name=='Villain']
    assert len(tokens)==2
    for c in tokens:
        ch=Plan(s.state,'p1',cards,None).ch(c)
        assert ch.pt==(2,1) and ch.colors=={'B'} and 'menace' in ch.keywords
    from app.game.errors import ActionError
    attacker=tokens[0]
    blocker=put(s,'Grizzly Bears','battlefield','p2')
    attack(s,[attacker],turn=4)
    to_phase(s,'declare_blockers')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':blocker.id,'attacker_id':attacker.id}])
    assert s.state.model_dump_json()==before
    roundtrip(s)


def test_vivi_actual_wizard_trigger_resolves_before_noncreature_spell(cards):
    s=setup(cards)
    cast(s,"Vivi's Persistence")
    token=next(c for c in s.state.cards.values() if c.is_token and c.name=='Wizard')
    assert Plan(s.state,'p1',cards,None).ch(token).pt==(0,1)
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,targets=['p2'],sources=[])
    for _ in range(20):
        if s.state.players['p3'].life==39:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert s.state.players['p2'].life==39 and s.state.players['p3'].life==39 and bolt.zone=='stack'
    settle(s)
    assert s.state.players['p2'].life==36
    roundtrip(s)


def test_fear_actual_enchantment_entry_optional_return(cards):
    s=setup(cards)
    source=put(s,'Fear of Infinity','graveyard')
    target=put(s,'Grizzly Bears','battlefield')
    cast(s,'Pacifism',targets=[target.id])
    answer(s,['yes'])
    assert source.zone=='p1:hand'
    roundtrip(s)


def test_fear_actual_full_unlock_only_not_first_door(cards):
    s=setup(cards)
    room=put(s,'Restricted Office // Lecture Hall','battlefield')
    source=put(s,'Fear of Infinity','graveyard')
    act(s,'p1',type='unlock_door',card_id=room.id,door=1)
    settle(s)
    assert source.zone=='p1:graveyard' and s.state.rules.decision is None
    act(s,'p1',type='unlock_door',card_id=room.id,door=2)
    settle(s)
    answer(s,['yes'])
    assert source.zone=='p1:hand'
    roundtrip(s)


def test_fear_decline_and_old_source_cannot_return(cards):
    s=setup(cards)
    source=put(s,'Fear of Infinity','graveyard')
    target=put(s,'Grizzly Bears','battlefield')
    cast(s,'Pacifism',targets=[target.id])
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'exile'})
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    answer(s,['yes'])
    assert source.zone=='p1:graveyard'
    roundtrip(s)


def test_fear_other_player_enchantment_entry_does_not_trigger(cards):
    s=setup(cards)
    source=put(s,'Fear of Infinity','graveyard')
    target=put(s,'Grizzly Bears','battlefield','p2')
    to_phase(s,'main1',2)
    mana(s,'p2')
    cast(s,'Pacifism',targets=[target.id],pid='p2')
    assert source.zone=='p1:graveyard' and s.state.rules.decision is None
    roundtrip(s)


def test_fear_actual_flying_lifelink_combat_and_cannot_block(cards):
    from app.game.errors import ActionError

    s=setup(cards)
    source=cast(s,'Fear of Infinity')
    cast(s,'Lightning Bolt',targets=['p1'])
    ground=put(s,'Grizzly Bears','battlefield','p2')
    attack(s,[source],turn=4)
    to_phase(s,'declare_blockers')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':ground.id,'attacker_id':source.id}])
    assert s.state.model_dump_json()==before
    act(s,'p2',type='declare_blockers',blocks=[])
    damage(s)
    assert s.state.players['p2'].life==38 and s.state.players['p1'].life==39
    to_phase(s,'declare_attackers',5)
    act(s,'p2',type='declare_attackers',attackers=[{'card_id':ground.id,'target':'p1'}])
    settle(s)
    to_phase(s,'declare_blockers')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='declare_blockers',blocks=[{'blocker_id':source.id,'attacker_id':ground.id}])
    assert s.state.model_dump_json()==before
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_expanded3_true_cold_pending_native_returns(cards,tmp_path,name):
    import subprocess
    import sys

    s=setup(cards)
    if name in PAYERS:
        source,_commander=reanimated_commander(s,name,True)
    else:
        source=put(s,name,'graveyard')
        host=put(s,'Grizzly Bears','battlefield')
        cast(s,'Pacifism',targets=[host.id])
    saved=tmp_path/'native-return.json'
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
name,source=sys.argv[3:5]
d=s.state.rules.decision
assert d is not None and d.player=='p1'
act(s,d.player,type='choose',decision_id=d.id,option_ids=['yes' if name=='Fear of Infinity' else 'pay'])
settle(s)
assert s.state.cards[source].zone=='p1:hand'
roundtrip(s)
repo.close()
"""
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),name,source.id],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=90,check=False)
    assert result.returncode==0,result.stdout+result.stderr
