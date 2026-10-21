"""Held exact two-line cycle predicate patch with native cycling, targets and draw order."""

import pytest

from tests import test_rules_delayed_blinks50 as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase

cards=gameplay.cards




def test_astral_native_cycle_self_triggers_from_graveyard_before_draw_then_returns_exact_target(cards):
    s=gameplay.gameplay.setup(cards,'Astral Drift')
    source=put(s,'Astral Drift','hand')
    target=put(s,'Grizzly Bears','battlefield')
    before=len(s.state.zones['p1:hand'])
    mana(s,W=1,C=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.rules.decision.resume['step']=='trigger_target'
    answer(s,[target.id])
    assert s.state.rules.decision.resume['step']=='may'
    assert len(s.state.zones['p1:hand'])==before-1
    answer(s,['yes'])
    assert s.state.cards[target.id].zone=='p1:exile'
    assert len(s.state.zones['p1:hand'])==before
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[target.id].zone=='p1:battlefield'
    roundtrip(s)


def test_astral_native_battlefield_other_cycle_targets_before_optional_exile(cards):
    s=gameplay.gameplay.setup(cards,'Astral Drift','Lonely Sandbar')
    source=put(s,'Astral Drift','battlefield')
    cycled=put(s,'Lonely Sandbar','hand')
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    mana(s,U=1)
    act(s,'p1',type='activate_ability',card_id=cycled.id,ability=2)
    assert s.state.rules.decision.resume['step']=='trigger_target'
    answer(s,[target.id])
    answer(s,['yes'])
    assert s.state.cards[target.id].zone=='p2:exile'
    assert s.state.cards[source.id].zone=='p1:battlefield'
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[target.id].zone=='p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('zone',['hand','graveyard','exile'])
def test_astral_other_cycle_does_not_trigger_from_nonbattlefield_source(cards,zone):
    s=gameplay.gameplay.setup(cards,'Astral Drift','Lonely Sandbar')
    put(s,'Astral Drift',zone)
    cycled=put(s,'Lonely Sandbar','hand')
    mana(s,U=1)
    act(s,'p1',type='activate_ability',card_id=cycled.id,ability=2)
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.rules.delayed
    roundtrip(s)


def test_astral_opponents_other_cycle_does_not_trigger(cards):
    s=gameplay.gameplay.setup(cards,'Astral Drift','Lonely Sandbar')
    put(s,'Astral Drift','battlefield')
    cycled=put(s,'Lonely Sandbar','hand',pid='p2')
    act(s,'p1',type='add_mana',player='p2',mana={'U':1})
    act(s,'p1',type='pass_priority')
    act(s,'p2',type='activate_ability',card_id=cycled.id,ability=2)
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.rules.delayed
    roundtrip(s)


def test_astral_illegal_announced_target_does_not_exile_but_cycling_still_draws(cards):
    from tests.test_rules_ordered_tutor_continuations import cast

    s=gameplay.gameplay.setup(cards,'Astral Drift','Murder')
    source=put(s,'Astral Drift','hand')
    target=put(s,'Grizzly Bears','battlefield')
    put(s,'Murder','hand')
    top=s.state.zones['p1:library'][0]
    mana(s,W=1,C=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
    cast(s,'Murder',targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone=='p1:graveyard'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.rules.decision is None
    assert not s.state.rules.delayed
    assert s.state.cards[top].zone=='p1:hand'
    roundtrip(s)


def test_astral_cycle_during_endstep_delays_until_following_endstep(cards):
    s=gameplay.gameplay.setup(cards,'Astral Drift')
    source=put(s,'Astral Drift','hand')
    target=put(s,'Grizzly Bears','battlefield')
    to_phase(s,'end',turn=1)
    mana(s,W=1,C=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    answer(s,[target.id])
    answer(s,['yes'])
    assert s.state.cards[target.id].zone=='p1:exile'
    to_phase(s,'main1',turn=2)
    assert s.state.cards[target.id].zone=='p1:exile'
    to_phase(s,'end',turn=2)
    settle(s)
    assert s.state.cards[target.id].zone=='p1:battlefield'
    roundtrip(s)


def test_astral_native_cycle_self_redirected_to_exile_still_triggers_and_may_decline(cards):
    s=gameplay.gameplay.setup(cards,'Astral Drift','Rest in Peace')
    put(s,'Rest in Peace','battlefield')
    source=put(s,'Astral Drift','hand')
    target=put(s,'Grizzly Bears','battlefield')
    old=s.state.rules.object_id(target.id)
    mana(s,W=1,C=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    assert s.state.cards[source.id].zone=='p1:exile'
    answer(s,[target.id])
    answer(s,['no'])
    assert s.state.cards[target.id].zone=='p1:battlefield'
    assert s.state.rules.object_id(target.id)==old
    assert not s.state.rules.delayed
    roundtrip(s)


def test_astral_whole_canonical_coverage(cards):
    from app.rules import coverage

    result=coverage.of_card_data(cards.resolve('Astral Drift'))
    assert result.level=='FULL',result


def test_astral_genuine_cold_cycle_to_target_then_optional_and_delayed_return(cards,tmp_path):
    s=gameplay.gameplay.setup(cards,'Astral Drift')
    source=put(s,'Astral Drift','hand')
    target=put(s,'Grizzly Bears','battlefield')
    mana(s,W=1,C=2)
    s=stage_fresh(s,cards,tmp_path/'cycle.json','p1',{'type':'activate_ability','card_id':source.id,'ability':1})
    assert s.state.rules.decision.resume['step']=='trigger_target'
    d=s.state.rules.decision
    s=stage_fresh(s,cards,tmp_path/'target.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[target.id]})
    assert s.state.rules.decision.resume['step']=='may'
    answer(s,['yes'])
    to_phase(s,'end',turn=1)
    s=stage_fresh(s,cards,tmp_path/'return.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.cards[target.id].zone=='p1:battlefield'
    roundtrip(s)


def stage_fresh(s,cards,path,actor,payload):
    import json
    import subprocess
    import sys
    from pathlib import Path

    from app.game.session import GameSession
    from app.game.state import GameState

    path.write_text(s.state.model_dump_json())
    code='''
import inspect,json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(path.parent/'images'))
s=GameSession(GameState.model_validate_json(path.read_text()),cards=repo)
s.perform(sys.argv[3],json.loads(sys.argv[4]))
while s.state.rules.decision is None and s.state.zones.get('stack'):
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
path.write_text(s.state.model_dump_json())
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),actor,json.dumps(payload)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    return GameSession(GameState.model_validate_json(path.read_text()),cards=cards)
