"""The upkeep player chooses exact card categories; native phasing owns all returns."""
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
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

REALM = 'Quest for Renewal'
DATA = json.loads((Path(__file__).parent/'fixtures/conditional_untap87_cards.json').read_text())
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
    s=table(cards,[*ALL,'Llanowar Elves'],ALL,ALL)
    to_phase(s,'main1',1)
    return s


def cast(s,name,pid='p1',targets=(),**kwargs):
    source=put(s,name,'hand',pid)
    mana(s,pid,C=20,W=10,U=10,G=10,R=10)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=list(targets),sources=[],**kwargs)
    settle(s)
    return source


@pytest.mark.parametrize('name',['Quest for Renewal','Venarian Gold'])
def test_canonical_native_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('count',[3,4,5])
def test_native_quest_current_counter_threshold_selects_creatures_only(cards,count):
    s=game(cards)
    source=cast(s,REALM)
    bear=put(s,'Grizzly Bears','battlefield')
    forest=put(s,'Forest','battlefield')
    act(s,'p1',type='counter',card_ids=[source.id],kind='quest',delta=count)
    # Resolve the real optional tapped-creature trigger without adding another counter.
    act(s,'p1',type='tap',card_ids=[bear.id,forest.id],tapped=True)
    from tests.test_rules_activated_copy_family import answer
    answer(s,optional=False)
    to_phase(s,'main1',2)
    assert s.state.cards[bear.id].tapped==(count<4)
    assert s.state.cards[forest.id].tapped
    roundtrip(s)


def test_native_gold_whole_x_cast_and_sleep_counter_consumption(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    aura=cast(s,'Venarian Gold',targets=[bear.id],x_value=1)
    assert s.state.cards[aura.id].zone=='p1:battlefield'
    assert s.state.cards[bear.id].counters.get('sleep',0)==1 and s.state.cards[bear.id].tapped
    to_phase(s,'main1',2)
    assert s.state.cards[bear.id].tapped and not s.state.cards[bear.id].counters.get('sleep',0)
    to_phase(s,'main1',5)
    assert not s.state.cards[bear.id].tapped
    roundtrip(s)


def test_native_real_tap_triggers_build_four_quest_counters(cards):
    from tests.test_rules_activated_copy_family import answer

    s=game(cards)
    source=cast(s,REALM)
    bear=put(s,'Llanowar Elves','battlefield')
    to_phase(s,'main1',4)
    for i in range(4):
        wait_priority(s,'p1')
        act(s,'p1',type='activate_ability',card_id=bear.id,ability=0)
        answer(s)
        assert s.state.cards[source.id].counters.get('quest',0)==i+1
        if i<3:
            act(s,'p1',type='tap',card_ids=[bear.id],tapped=False)
    to_phase(s,'main1',5)
    assert not s.state.cards[bear.id].tapped
    roundtrip(s)


def test_native_tapped_entry_does_not_trigger_and_other_step_ignores_own_restriction(cards):
    from tests.test_rules_activated_copy_family import answer

    s=game(cards)
    source=cast(s,REALM)
    titan=cast(s,'Deep-Slumber Titan')
    assert s.state.cards[titan.id].tapped and not s.state.cards[source.id].counters.get('quest',0)
    act(s,'p1',type='counter',card_ids=[source.id],kind='quest',delta=4)
    to_phase(s,'main1',2)
    assert not s.state.cards[titan.id].tapped
    act(s,'p1',type='tap',card_ids=[titan.id],tapped=True)
    answer(s,optional=False)
    to_phase(s,'main1',3)
    act(s,'p1',type='tap',card_ids=[titan.id],tapped=True)
    answer(s,optional=False)
    to_phase(s,'main1',4)
    assert s.state.cards[titan.id].tapped
    roundtrip(s)


def test_native_two_quests_remove_only_one_stun_and_threshold_rechecks(cards):
    from tests.test_rules_activated_copy_family import answer

    s=game(cards)
    first=cast(s,REALM)
    second=put(s,REALM,'battlefield','p2')
    act(s,'p2',type='set_controller',card_ids=[second.id],player='p1')
    assert first.id!=second.id
    bear=put(s,'Grizzly Bears','battlefield')
    for source in (first,second):
        act(s,'p1',type='counter',card_ids=[source.id],kind='quest',delta=4)
    act(s,'p1',type='tap',card_ids=[bear.id],tapped=True)
    answer(s,optional=False)
    act(s,'p1',type='counter',card_ids=[bear.id],kind='stun',delta=2)
    to_phase(s,'main1',2)
    assert s.state.cards[bear.id].tapped and s.state.cards[bear.id].counters.get('stun',0)==1
    for source in (first,second):
        act(s,'p1',type='counter',card_ids=[source.id],kind='quest',delta=-1)
    to_phase(s,'main1',3)
    assert s.state.cards[bear.id].tapped and s.state.cards[bear.id].counters.get('stun',0)==1
    roundtrip(s)


def test_native_gold_moves_without_moving_counters_and_checks_current_host(cards):
    s=game(cards)
    original=put(s,'Grizzly Bears','battlefield','p2')
    other=put(s,'Grizzly Bears','battlefield','p3')
    aura=cast(s,'Venarian Gold',targets=[original.id],x_value=1)
    act(s,'p1',type='attach',card_ids=[aura.id],to=other.id)
    assert s.state.cards[original.id].counters.get('sleep',0)==1
    assert not s.state.cards[other.id].counters.get('sleep',0)
    act(s,'p3',type='tap',card_ids=[other.id],tapped=True)
    to_phase(s,'main1',2)
    assert not s.state.cards[original.id].tapped
    to_phase(s,'main1',3)
    assert not s.state.cards[other.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('mode',['quest','gold'])
def test_true_cold_conditional_untap_state(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    import app

    s=game(cards)
    if mode=='quest':
        source=cast(s,REALM)
        bear=put(s,'Grizzly Bears','battlefield')
        act(s,'p1',type='counter',card_ids=[source.id],kind='quest',delta=4)
        act(s,'p1',type='tap',card_ids=[bear.id],tapped=True)
        from tests.test_rules_activated_copy_family import answer
        answer(s,optional=False)
    else:
        bear=put(s,'Grizzly Bears','battlefield','p2')
        cast(s,'Venarian Gold',targets=[bear.id],x_value=1)
    saved=tmp_path/'untap.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
bear,mode=sys.argv[3:]
to_phase(s,'main1',2)
assert s.state.cards[bear].tapped==(mode=='gold')
if mode=='gold':
 assert not s.state.cards[bear].counters.get('sleep',0)
 to_phase(s,'main1',5)
 assert not s.state.cards[bear].tapped
roundtrip(s);repo.close()
'''
    backend=Path(app.__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),bear.id,mode],cwd=backend,
                          env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr
