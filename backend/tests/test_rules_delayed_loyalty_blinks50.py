"""Unimported Kaya allprinted native choices and simultaneous discard preparation."""
import pytest

from tests import test_rules_delayed_blinks50 as gameplay
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

cards=gameplay.cards




def kaya(cards,*extra):
    s=gameplay.gameplay.setup(cards,'Kaya, Ghost Assassin',*extra)
    cast(s,'Kaya, Ghost Assassin')
    source=next(c for c in s.state.cards.values() if c.name=='Kaya, Ghost Assassin' and c.zone=='p1:battlefield')
    return s,source


@pytest.mark.parametrize('use_self',[False,True])
def test_kaya_announces_creature_then_resolution_chooses_self_or_that_creature(cards,use_self):
    s,source=kaya(cards)
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[target.id],target_counts=[1])
    settle(s)
    assert s.state.rules.decision.resume['step']=='kaya_blink50'
    chosen=source if use_self else target
    other=target if use_self else source
    answer(s,[chosen.id])
    assert s.state.cards[chosen.id].zone==chosen.owner+':exile'
    assert s.state.cards[other.id].zone.endswith(':battlefield')
    assert s.state.players['p1'].life==38
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[chosen.id].zone==chosen.owner+':battlefield'
    roundtrip(s)


def test_kaya_zero_target_source_gone_still_loses_two_without_exile(cards):
    s,source=kaya(cards,"Hero's Downfall")
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[],target_counts=[0])
    cast(s,"Hero's Downfall",targets=[source.id])
    settle(s)
    assert s.state.players['p1'].life==38
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert not s.state.rules.delayed
    roundtrip(s)


def test_kaya_illegal_announced_creature_counters_ability_including_life_loss(cards):
    s,source=kaya(cards,'Murder')
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[target.id],target_counts=[1])
    cast(s,'Murder',targets=[target.id])
    settle(s)
    assert s.state.players['p1'].life==40
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert not s.state.rules.delayed
    roundtrip(s)


def test_kaya_minus_one_native_each_opponent_loses_and_you_gain(cards):
    s,source=kaya(cards)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    settle(s)
    assert s.state.players['p1'].life==42
    assert s.state.players['p2'].life==38 and s.state.players['p3'].life==38
    assert s.state.cards[source.id].counters['loyalty']==4
    roundtrip(s)


def test_kaya_minus_two_private_choices_then_actual_simultaneous_discard_before_draw(cards):
    from app.game.visibility import can_see

    s,source=kaya(cards)
    second=[put(s,n,'hand',pid='p2') for n in ('Grizzly Bears','Divination')]
    third=[put(s,n,'hand',pid='p3') for n in ('Grizzly Bears','Divination')]
    before=len(s.state.zones['p1:hand'])
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    settle(s)
    assert s.state.rules.decision.player=='p2'
    answer(s,[second[0].id])
    assert s.state.rules.decision.player=='p3'
    assert s.state.cards[second[0].id].zone=='p2:hand'
    assert not can_see(s.state,s.state.cards[second[0].id],'p3')
    assert not can_see(s.state,s.state.cards[second[0].id],'p1')
    answer(s,[third[0].id])
    assert s.state.cards[second[0].id].zone=='p2:graveyard'
    assert s.state.cards[third[0].id].zone=='p3:graveyard'
    assert len(s.state.zones['p1:hand'])==before+1
    events=[e for e in s.state.rules.events if e.kind=='zone_change' and e.card in (second[0].id,third[0].id) and e.from_zone and e.from_zone.endswith(':hand')]
    assert len(events)==2 and len({e.batch for e in events})==1
    roundtrip(s)


def test_kaya_cold_resolution_self_choice_then_cold_delayed_return(cards,tmp_path):
    s,source=kaya(cards)
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[target.id],target_counts=[1])
    settle(s)
    d=s.state.rules.decision
    s=stage_fresh(s,cards,tmp_path/'choose.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[source.id]})
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.players['p1'].life==38
    to_phase(s,'upkeep',turn=4)
    s=stage_fresh(s,cards,tmp_path/'return.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)


def test_kaya_native_cold_private_second_discard_then_one_simultaneous_event(cards,tmp_path):
    from app.game.visibility import can_see
    from tests.test_rules_exile_outcomes42_cold import fresh

    s,source=kaya(cards)
    second=[put(s,n,'hand',pid='p2') for n in ('Grizzly Bears','Divination')]
    third=[put(s,n,'hand',pid='p3') for n in ('Grizzly Bears','Divination')]
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    settle(s)
    answer(s,[second[0].id])
    assert s.state.cards[second[0].id].zone=='p2:hand'
    assert not can_see(s.state,s.state.cards[second[0].id],'p3')
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'discard.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[third[0].id]})
    events=[e for e in s.state.rules.events if e.kind=='zone_change' and e.card in (second[0].id,third[0].id) and e.from_zone and e.from_zone.endswith(':hand')]
    assert len(events)==2 and len({e.batch for e in events})==1
    assert s.state.rules.decision is None
    roundtrip(s)


def test_kaya_whole_canonical_coverage(cards):
    from app.rules import coverage

    result=coverage.of_card_data(cards.resolve('Kaya, Ghost Assassin'))
    assert result.level=='FULL',result


def stage_fresh(s,cards,path,actor,payload):
    import json
    import subprocess
    import sys
    from pathlib import Path

    from app.game.session import GameSession
    from app.game.state import GameState

    path.write_text(s.state.model_dump_json())
    code='''
import json,sys
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
