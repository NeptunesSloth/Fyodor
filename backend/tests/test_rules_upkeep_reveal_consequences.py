"""Canonical Aura-host and permanent-copy consequences of mandatory upkeep reveals."""
from __future__ import annotations

# ruff: noqa: F811 -- native fixture imported for pytest discovery.
import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_reveal_consequences import cards, cast  # noqa: F401
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase


@pytest.mark.parametrize('name',['Paroxysm',"Shapeshifter's Marrow"])
def test_canonical_full(cards,name):
    result=coverage.of_card_data(cards.resolve(name))
    assert result.level=='FULL',result.manual_parts


def setup_aura(cards,land=False):
    s=table(cards,['Paroxysm'],['Grizzly Bears','Forest','Sol Ring'])
    host=put(s,'Grizzly Bears','battlefield','p2')
    source=cast(s,'Paroxysm',[host.id])
    shown=put(s,'Forest' if land else 'Sol Ring','library','p2')
    return s,source,host,shown


@pytest.mark.parametrize('land',[False,True])
def test_paroxysm_actual_host_controller_upkeep_mandatory_destroy_or_timed_pump(cards,land):
    s,source,host,shown=setup_aura(cards,land)
    to_phase(s,'upkeep',turn=2)
    settle(s)
    assert s.state.cards[shown.id].zone=='p2:library'
    assert not s.state.cards[shown.id].revealed_to
    if land:
        assert s.state.cards[host.id].zone=='p2:graveyard'
        assert s.state.cards[source.id].zone=='p1:graveyard'
    else:
        assert chars(s,s.state.cards[host.id]).pt==(5,5)
        to_phase(s,'upkeep',turn=3)
        settle(s)
        assert chars(s,s.state.cards[host.id]).pt==(2,2)
    roundtrip(s)


@pytest.mark.parametrize('change',['aura_leaves','host_blinks','host_control'])
def test_paroxysm_preserves_original_host_and_upkeep_player_bindings(cards,change):
    s,source,host,shown=setup_aura(cards)
    to_phase(s,'upkeep',turn=2)
    assert s.state.zones['stack']
    if change=='aura_leaves':
        act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    elif change=='host_blinks':
        act(s,'p2',type='move',card_ids=[host.id],to={'player':'p2','zone':'hand'})
        act(s,'p2',type='move',card_ids=[host.id],to={'player':'p2','zone':'battlefield'})
    else:
        act(s,'p2',type='set_controller',card_ids=[host.id],player='p3')
    settle(s)
    assert chars(s,s.state.cards[host.id]).pt==((2,2) if change=='host_blinks' else (5,5))
    assert s.state.cards[shown.id].zone=='p2:library'
    assert not s.state.cards[shown.id].revealed_to
    roundtrip(s)


@pytest.mark.parametrize('creature',[False,True])
def test_marrow_opponent_reveal_native_permanent_copy_or_unchanged_enchantment(cards,creature):
    s=table(cards,["Shapeshifter's Marrow"],['Grizzly Bears','Sol Ring'])
    source=cast(s,"Shapeshifter's Marrow")
    shown=put(s,'Grizzly Bears' if creature else 'Sol Ring','library','p2')
    to_phase(s,'upkeep',turn=2)
    settle(s)
    if creature:
        assert s.state.cards[shown.id].zone=='p2:graveyard'
        assert chars(s,s.state.cards[source.id]).name=='Grizzly Bears'
        assert chars(s,s.state.cards[source.id]).pt==(2,2)
        assert 'Enchantment' not in chars(s,s.state.cards[source.id]).types
        assert not any('upkeep' in a.text for a in chars(s,s.state.cards[source.id]).abilities)
    else:
        assert s.state.cards[shown.id].zone=='p2:library'
        assert chars(s,s.state.cards[source.id]).name=="Shapeshifter's Marrow"
    assert not s.state.cards[shown.id].revealed_to
    roundtrip(s)


def test_marrow_old_source_incarnation_not_replaced_new_one_still_reveals_and_mills(cards):
    s=table(cards,["Shapeshifter's Marrow"],['Grizzly Bears'])
    source=cast(s,"Shapeshifter's Marrow")
    shown=put(s,'Grizzly Bears','library','p2')
    to_phase(s,'upkeep',turn=2)
    assert s.state.zones['stack']
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'hand'})
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'battlefield'})
    settle(s)
    assert s.state.cards[shown.id].zone=='p2:graveyard'
    assert chars(s,s.state.cards[source.id]).name=="Shapeshifter's Marrow"
    roundtrip(s)


def test_marrow_recipe_copies_cda_not_revealed_derived_power(cards):
    s=table(cards,["Shapeshifter's Marrow"],['Lhurgoyf'])
    source=cast(s,"Shapeshifter's Marrow")
    shown=put(s,'Lhurgoyf','library','p2')
    to_phase(s,'upkeep',turn=2)
    settle(s)
    assert s.state.cards[shown.id].zone=='p2:graveyard'
    assert chars(s,s.state.cards[source.id]).name=='Lhurgoyf'
    assert chars(s,s.state.cards[source.id]).pt==(1,2)
    roundtrip(s)


def test_marrow_graveyard_replacement_does_not_lose_revealed_copy_recipe(cards):
    s=table(cards,["Shapeshifter's Marrow",'Rest in Peace'],['Grizzly Bears'])
    source=cast(s,"Shapeshifter's Marrow")
    cast(s,'Rest in Peace')
    shown=put(s,'Grizzly Bears','library','p2')
    to_phase(s,'upkeep',turn=2)
    settle(s)
    assert s.state.cards[shown.id].zone=='p2:exile'
    assert chars(s,s.state.cards[source.id]).name=='Grizzly Bears'
    assert chars(s,s.state.cards[source.id]).pt==(2,2)
    roundtrip(s)


@pytest.mark.parametrize('mode',['host','copy'])
def test_upkeep_reveal_source_and_host_bindings_resume_in_fresh_process(cards,tmp_path,mode):
    import subprocess
    import sys
    from pathlib import Path
    if mode=='host':
        s,source,host,shown=setup_aura(cards)
        to_phase(s,'upkeep',turn=2)
        act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
        expected=host.id
    else:
        s=table(cards,["Shapeshifter's Marrow",'Rest in Peace'],['Lhurgoyf'])
        source=cast(s,"Shapeshifter's Marrow")
        cast(s,'Rest in Peace')
        shown=put(s,'Lhurgoyf','library','p2')
        to_phase(s,'upkeep',turn=2)
        expected=source.id
    assert s.state.zones['stack']
    saved=tmp_path/f'{mode}.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_wave6c_tokens_pumps import chars
save,db,expected,shown,mode=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
for _ in range(40):
 d=s.state.rules.decision
 if d:s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[d.options[0].id]})
 elif s.state.zones['stack']:s.perform(s.state.rules.priority,{'type':'pass_priority'})
 else:break
else:raise AssertionError('did not finish')
ch=chars(s,s.state.cards[expected])
if mode=='host':
 assert ch.pt==(5,5)
 assert s.state.cards[shown].zone=='p2:library'
else:
 assert ch.name=='Lhurgoyf'
 assert ch.pt==(0,1)
 assert s.state.cards[shown].zone=='p2:exile'
assert not s.state.cards[shown].revealed_to
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),expected,shown.id,mode],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
