"""Oath targets compare to the original active player; the ability retains its source controller."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Oath of Ghouls','Oath of Scholars','Oath of Mages']
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_upkeep_comparison75_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def choose(s, ids, settle_after=True):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    if settle_after:
        settle(s)


def clear(s, pid, zone):
    ids = list(s.state.zones[pid+':'+zone])
    if ids:
        act(s, pid, type='move', card_ids=ids, to={'player':pid,'zone':'exile'})


def cast(s, name, pool, targets=(), pid='p1', **kwargs):
    wait_priority(s,pid)
    source = put(s,name,'hand',pid)
    mana(s,pid=pid,**pool)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=list(targets),sources=[],**kwargs)
    settle(s)
    return source


def setup(cards, name, qualifies=True, ward=False):
    names = [c['name'] for c in DATA]
    s = table(cards,names,names,names)
    start(s)
    act(s,'p1',type='set_prefs',hold_priority=True)
    source = cast(s,name,{'C':3,'B':1,'U':1,'R':1})
    for pid in ['p1','p2','p3']:
        clear(s,pid,'hand')
    selected = None
    if name=='Oath of Ghouls':
        if qualifies:
            selected = put(s,'Grizzly Bears','graveyard','p2')
            put(s,'Llanowar Elves','graveyard','p2')
            put(s,'Typhoid Rats','graveyard','p3')
    elif name=='Oath of Scholars':
        put(s,'Grizzly Bears','hand','p3')
        if not qualifies:
            put(s,'Grizzly Bears','hand','p2')
    else:
        act(s,'p2',type='set_life',player='p2',value=39 if qualifies else 40)
    if ward:
        put(s,'Leyline of Sanctity','battlefield','p1')
        put(s,'Leyline of Sanctity','battlefield','p3')
    return s, source, selected


def upkeep(s):
    to_phase(s,'upkeep',turn=5)
    settle(s)
    return s.state.rules.decision


def check_result(s,name,selected):
    if name=='Oath of Ghouls':
        if (d:=s.state.rules.decision) is not None:
            assert d.player=='p2'
            choose(s,[selected.id])
        assert s.state.cards[selected.id].zone=='p2:hand'
    elif name=='Oath of Scholars':
        assert len(s.state.zones['p2:hand'])==3
    else:
        assert s.state.players['p3'].life==39
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('name',NAMES)
def test_paid_source_active_player_targets_and_optionally_performs_native_effect(cards,name):
    s,_,selected=setup(cards,name)
    d=upkeep(s)
    assert d is not None and d.player=='p2'
    options={o.id for o in d.options}
    assert 'p3' in options and 'p2' not in options
    choose(s,['p3'])
    d=s.state.rules.decision
    assert d is not None and d.player=='p2' and d.resume['step']=='may'
    choose(s,['yes'])
    check_result(s,name,selected)


@pytest.mark.parametrize('name',NAMES)
def test_equal_quantities_are_not_legal_targets(cards,name):
    s,_,_=setup(cards,name,qualifies=False)
    d=upkeep(s)
    assert d is None
    assert not s.state.rules.stack
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_active_player_can_decline_without_affecting_other_players(cards,name):
    s,_,selected=setup(cards,name)
    upkeep(s)
    choose(s,['p3'])
    before={pid:s.state.players[pid].life for pid in ['p1','p2','p3']}
    choose(s,['no'])
    if selected:
        assert selected.zone=='p2:graveyard'
    assert not s.state.zones['p2:hand']
    assert {pid:s.state.players[pid].life for pid in before}==before
    roundtrip(s)


def test_targeting_authority_remains_source_controller_despite_different_target_chooser(cards):
    s,_,_=setup(cards,'Oath of Mages',ward=True)
    d=upkeep(s)
    assert d is not None and d.player=='p2'
    assert {o.id for o in d.options}=={'p1'}
    choose(s,['p1'])
    choose(s,['yes'])
    assert s.state.players['p1'].life==39 and s.state.players['p3'].life==40
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_comparison_is_rechecked_after_actual_native_spell_changes_quantity(cards,name):
    s,source,selected=setup(cards,name)
    upkeep(s)
    choose(s,['p3'],settle_after=False)
    if name=='Oath of Ghouls':
        cast(s,'Cremate',{'B':1},[selected.id])
        assert selected.zone=='p2:exile'
        assert len([c for c in s.state.cards.values() if c.zone=='p2:graveyard'])==1
    elif name=='Oath of Scholars':
        cast(s,'Think Twice',{'C':1,'U':1},pid='p2')
        assert len(s.state.zones['p2:hand'])==1
    else:
        cast(s,'Lightning Bolt',{'R':1},['p3'])
        assert s.state.players['p3'].life==37
    assert s.state.rules.decision is None and not s.state.rules.stack
    assert not any(e.source_card==source.id for e in s.state.rules.stack.values())
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_true_cold_source_gone_keeps_active_player_optional_effect_and_controller(cards,tmp_path,name):
    import subprocess
    import sys

    import app

    s,source,selected=setup(cards,name)
    upkeep(s)
    choose(s,['p3'],settle_after=False)
    cast(s,'Disenchant',{'C':1,'W':1},[source.id])
    assert source.zone=='p1:graveyard'
    d=s.state.rules.decision
    assert d is not None and d.player=='p2' and d.resume['step']=='may'
    saved=tmp_path/'oath.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
d=s.state.rules.decision
assert d is not None and d.player=='p2'
act(s,'p2',type='choose',decision_id=d.id,option_ids=['yes'])
settle(s)
name,selected=sys.argv[3:]
if name=='Oath of Ghouls':
 d=s.state.rules.decision
 if d is not None:
  assert d.player=='p2'
  act(s,'p2',type='choose',decision_id=d.id,option_ids=[selected])
  settle(s)
 assert s.state.cards[selected].zone=='p2:hand'
elif name=='Oath of Scholars':assert len(s.state.zones['p2:hand'])==3
else:assert s.state.players['p3'].life==39
assert s.state.rules.decision is None
roundtrip(s)
'''
    p=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),name,selected.id if selected else ''],
                     capture_output=True,text=True,timeout=90,cwd=Path(app.__file__).resolve().parents[1])
    assert p.returncode==0,p.stdout+p.stderr


def test_actual_copy_keeps_original_active_comparison_and_optional_player(cards):
    s,source,_=setup(cards,'Oath of Mages')
    for pid,life in [('p1',37),('p2',35),('p3',40)]:
        act(s,pid,type='set_life',player=pid,value=life)
    upkeep(s)
    choose(s,['p1'],settle_after=False)
    original=next(sid for sid,e in s.state.rules.stack.items() if e.source_card==source.id)
    cast(s,'Return the Favor',{'C':1,'R':2},[original],pid='p3',modes=[0])
    d=s.state.rules.decision
    assert d is not None and d.player=='p3' and d.resume['step']=='copy_target'
    choose(s,['keep'],settle_after=False)
    copy=next(e for sid,e in s.state.rules.stack.items() if e.source_card==source.id and sid!=original)
    assert copy.controller=='p3'
    cast(s,'Stifle',{'U':1},[original])
    d=s.state.rules.decision
    assert d is not None and d.player=='p2' and d.resume['step']=='may'
    choose(s,['yes'])
    assert s.state.players['p1'].life==36
    assert s.state.players['p2'].life==35 and s.state.players['p3'].life==40
    assert s.state.rules.decision is None and not s.state.rules.stack
    roundtrip(s)


def test_scholars_actually_discards_nonempty_active_hand_before_drawing_three(cards):
    s,_,_=setup(cards,'Oath of Scholars')
    original=put(s,'Grizzly Bears','hand','p2')
    put(s,'Llanowar Elves','hand','p3')
    upkeep(s)
    choose(s,['p3'])
    choose(s,['yes'])
    assert s.state.cards[original.id].zone=='p2:graveyard'
    assert len(s.state.zones['p2:hand'])==3
    roundtrip(s)
