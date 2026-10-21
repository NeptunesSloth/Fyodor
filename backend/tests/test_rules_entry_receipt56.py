"""Actual optional source counters pay before reflexive target selection."""
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

NAMES=['Back for More','Jailbreak']


@pytest.fixture
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/entry_receipt56_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='oc55',number=str(i),**{k:v for k,v in c.items() if k not in ('name','set_code')})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,name,*,target_name='Grizzly Bears'):
    names=[*NAMES,'Grizzly Bears','Sol Ring','Pacifism','Forest',"Grafdigger's Cage",'Clone','Ornithopter','Torpor Orb','Panharmonicon','Lake of the Dead','Lightning Bolt','March of the Machines']
    s=table(cards,names,names,names)
    to_phase(s,'main1',1)
    target=put(s,target_name,'graveyard','p2' if name=='Jailbreak' else 'p1')
    own=put(s,'Sol Ring','graveyard')
    opposing=put(s,'Grizzly Bears','battlefield','p3')
    spell=put(s,name,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'G':10,'B':10,'W':10,'C':10,'R':10})
    return s,spell,target,own,opposing


def cast(s,spell,target):
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[target.id],sources=[])
    settle(s)


def answer(s,ids):
    d=s.state.rules.decision
    assert d is not None
    act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
    settle(s)


def test_back_actual_return_then_late_fight(cards):
    s,spell,target,_own,opposing=setup(cards,'Back for More')
    cast(s,spell,target)
    assert target.zone=='p1:battlefield'
    d=s.state.rules.decision
    assert d is not None and d.resume.get('step')=='trigger_group' and opposing.id in [o.id for o in d.options]
    answer(s,[opposing.id])
    assert target.zone=='p1:graveyard' and opposing.zone=='p3:graveyard'
    roundtrip(s)


def test_jail_actual_owner_return_then_late_own_value_target(cards):
    s,spell,target,own,_opposing=setup(cards,'Jailbreak')
    cast(s,spell,target)
    assert target.zone=='p2:battlefield'
    d=s.state.rules.decision
    assert d is not None and d.resume.get('step')=='trigger_group' and own.id in [o.id for o in d.options]
    answer(s,[own.id])
    assert own.zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_cage_prevents_entry_so_no_reflexive_target(cards,name):
    s,spell,target,own,_opposing=setup(cards,name)
    put(s,"Grafdigger's Cage",'battlefield')
    cast(s,spell,target)
    assert target.zone.endswith(':graveyard') and s.state.rules.decision is None
    assert own.zone=='p1:graveyard'
    roundtrip(s)


def test_jail_aura_entry_host_choice_precedes_reflexive_target(cards):
    s,spell,target,own,opposing=setup(cards,'Jailbreak',target_name='Pacifism')
    put(s,'Grizzly Bears','battlefield','p1')
    cast(s,spell,target)
    d=s.state.rules.decision
    assert d is not None and d.player=='p2' and target.zone=='p2:graveyard'
    assert opposing.id in [o.id for o in d.options]
    answer(s,[opposing.id])
    assert target.zone=='p2:battlefield' and target.attached_to==opposing.id
    d=s.state.rules.decision
    assert d is not None and d.player=='p1' and own.id in [o.id for o in d.options]
    answer(s,[own.id])
    assert own.zone=='p1:battlefield'
    roundtrip(s)


def test_jail_aura_no_host_stays_graveyard_and_does_not_trigger(cards):
    s,spell,target,own,opposing=setup(cards,'Jailbreak',target_name='Pacifism')
    act(s,'p1',type='move',card_ids=[opposing.id],to={'player':'p3','zone':'exile'})
    cast(s,spell,target)
    assert target.zone=='p2:graveyard' and own.zone=='p1:graveyard' and s.state.rules.decision is None
    roundtrip(s)


def test_back_original_returned_object_leaves_and_returns_no_fight(cards):
    s,spell,target,_own,opposing=setup(cards,'Back for More')
    cast(s,spell,target)
    act(s,'p1',type='set_prefs',hold_priority=True)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[opposing.id])
    act(s,'p1',type='move',card_ids=[target.id],to={'player':'p1','zone':'exile'})
    act(s,'p1',type='move',card_ids=[target.id],to={'player':'p1','zone':'battlefield'})
    settle(s)
    assert target.zone=='p1:battlefield' and opposing.zone=='p3:battlefield'
    assert not target.damage and not opposing.damage
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_initial_target_gone_fizzles_and_no_reflexive(cards,name):
    s,spell,target,own,_opposing=setup(cards,name)
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[target.id],sources=[])
    act(s,'p1',type='move',card_ids=[target.id],to={'player':target.owner,'zone':'exile'})
    settle(s)
    assert target.zone.endswith(':exile') and own.zone=='p1:graveyard' and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_reflexive_up_to_zero_targets(cards,name):
    s,spell,target,own,opposing=setup(cards,name)
    cast(s,spell,target)
    answer(s,[])
    assert target.zone.endswith(':battlefield') and own.zone=='p1:graveyard' and opposing.zone=='p3:battlefield'
    roundtrip(s)


def test_jail_clone_as_entered_value_not_printed_value(cards):
    s,spell,target,own,opposing=setup(cards,'Jailbreak',target_name='Clone')
    too_large=put(s,'Clone','graveyard','p1')
    cast(s,spell,target)
    d=s.state.rules.decision
    assert d is not None
    assert opposing.id in [o.id for o in d.options]
    answer(s,[opposing.id])
    d=s.state.rules.decision
    assert d is not None and own.id in [o.id for o in d.options] and too_large.id not in [o.id for o in d.options]
    answer(s,[own.id])
    assert own.zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('aura_pause',[False,True])
def test_actual_cold_restores_entry_receipt_and_late_target(cards,tmp_path,aura_pause):
    import subprocess
    import sys

    s,spell,target,own,opposing=setup(cards,'Jailbreak',target_name='Pacifism' if aura_pause else 'Grizzly Bears')
    if aura_pause:
        put(s,'Grizzly Bears','battlefield','p1')
    cast(s,spell,target)
    saved=tmp_path/'entry-choice.json'
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
target,own,host=sys.argv[3:6]
if sys.argv[6]=='True':
 d=s.state.rules.decision
 assert d.player=='p2' and s.state.cards[target].zone=='p2:graveyard'
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[host])
 settle(s)
 assert s.state.cards[target].attached_to==host
assert s.state.cards[target].zone=='p2:battlefield'
d=s.state.rules.decision
assert d is not None and d.player=='p1' and own in [o.id for o in d.options]
act(s,d.player,type='choose',decision_id=d.id,option_ids=[own])
settle(s)
assert s.state.cards[own].zone=='p1:battlefield'
roundtrip(s)
repo.close()
"""
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),target.id,own.id,opposing.id,str(aura_pause)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=90,check=False)
    assert result.returncode==0,result.stdout+result.stderr


def test_jail_entered_clone_dies_to_sba_still_creates_reflexive(cards):
    s,spell,target,own,_opposing=setup(cards,'Jailbreak',target_name='Clone')
    cast(s,spell,target)
    answer(s,['none'])
    assert target.zone=='p2:graveyard'
    d=s.state.rules.decision
    assert d is not None and own.id in [o.id for o in d.options]
    answer(s,[own.id])
    assert own.zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('target_name',['Grizzly Bears','Sol Ring'])
def test_jail_torpor_orb_reads_actual_entered_creature_type(cards,target_name):
    s,spell,target,own,_opposing=setup(cards,'Jailbreak',target_name=target_name)
    put(s,'Torpor Orb','battlefield')
    cast(s,spell,target)
    assert target.zone=='p2:battlefield'
    if target_name=='Grizzly Bears':
        assert s.state.rules.decision is None and own.zone=='p1:graveyard'
    else:
        d=s.state.rules.decision
        assert d is not None and own.id in [o.id for o in d.options]
        answer(s,[own.id])
        assert own.zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_panharmonicon_does_not_multiply_spell_reflexive(cards,name):
    s,spell,target,_own,_opposing=setup(cards,name)
    put(s,'Panharmonicon','battlefield')
    cast(s,spell,target)
    answer(s,[])
    assert s.state.rules.decision is None and not s.state.zones.get('stack') and not s.state.rules.pending_triggers
    roundtrip(s)


def test_jail_actual_lake_of_the_dead_entry_payment_diversion_is_not_entry(cards):
    s,spell,target,own,_opposing=setup(cards,'Jailbreak',target_name='Lake of the Dead')
    zero=put(s,'Forest','graveyard')
    cast(s,spell,target)
    assert target.zone=='p2:graveyard' and own.zone=='p1:graveyard' and zero.zone=='p1:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_aura_entry_private_choice_rejects_unrelated_spell_without_mutation(cards):
    from app.game.errors import ActionError

    s,spell,target,_own,opposing=setup(cards,'Jailbreak',target_name='Pacifism')
    put(s,'Grizzly Bears','battlefield','p1')
    bolt=put(s,'Lightning Bolt','hand')
    cast(s,spell,target)
    assert s.state.rules.decision is not None and s.state.rules.decision.player=='p2'
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=bolt.id,targets=[opposing.id],sources=[])
    assert s.state.model_dump_json()==before
    answer(s,[opposing.id])
    assert target.zone=='p2:battlefield'
    answer(s,[])
    roundtrip(s)


def test_jail_torpor_reads_continuous_creature_type_as_entered(cards):
    s,spell,target,own,_opposing=setup(cards,'Jailbreak',target_name='Sol Ring')
    put(s,'Torpor Orb','battlefield')
    put(s,'March of the Machines','battlefield')
    cast(s,spell,target)
    assert target.zone=='p2:battlefield' and 'Creature' in Plan(s.state,'p1',cards,None).ch(target).types
    assert s.state.rules.decision is None and own.zone=='p1:graveyard'
    roundtrip(s)
