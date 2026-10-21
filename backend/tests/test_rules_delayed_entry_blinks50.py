"""Isolated native incoming-land tapped kernel and unimported exact Surfer leaf."""

import pytest

from app.rules import replacements
from tests import test_rules_delayed_blinks50 as gameplay
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

cards=gameplay.cards




def surfer(s,targets):
    cast(s,'Silver Surfer, Cosmic Voyager')
    d=s.state.rules.decision
    if d is not None:
        assert d.resume['step']=='trigger_group'
        answer(s,targets)
    else:
        assert not targets
    return next(c for c in s.state.cards.values() if c.name=='Silver Surfer, Cosmic Voyager' and c.zone=='p1:battlefield')


def test_surfer_actual_simultaneous_owner_return_lands_tapped_nonlands_untapped_after_source_gone(cards):
    s=gameplay.gameplay.setup(cards,'Silver Surfer, Cosmic Voyager','Murder')
    land=put(s,'Forest','battlefield')
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    act(s,'p1',type='set_controller',card_ids=[bear.id],player='p1')
    source=surfer(s,[land.id,bear.id])
    assert s.state.cards[land.id].zone=='p1:exile'
    assert s.state.cards[bear.id].zone=='p2:exile'
    cast(s,'Murder',targets=[source.id])
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[land.id].zone=='p1:battlefield' and s.state.cards[land.id].tapped
    assert s.state.cards[bear.id].zone=='p2:battlefield' and not s.state.cards[bear.id].tapped
    events=[e for e in s.state.rules.events if e.kind=='zone_change' and e.card in (land.id,bear.id) and e.to_zone and e.to_zone.endswith(':battlefield')]
    assert len({e.batch for e in events[-2:]})==1
    roundtrip(s)


def test_surfer_clone_as_land_after_copy_choice_enters_tapped_with_other_returns_waiting(cards):
    s=gameplay.gameplay.setup(cards,'Silver Surfer, Cosmic Voyager','Clone','Dryad Arbor')
    bear=put(s,'Grizzly Bears','battlefield')
    arbor=put(s,'Dryad Arbor','battlefield')
    forest=put(s,'Forest','battlefield')
    clone=cast(s,'Clone')
    answer(s,[bear.id])
    surfer(s,[clone.id,forest.id,bear.id])
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.rules.decision is not None
    assert all(s.state.cards[cid].zone.endswith(':exile') for cid in (clone.id,forest.id,bear.id))
    answer(s,[arbor.id])
    assert s.state.cards[clone.id].zone=='p1:battlefield' and s.state.cards[clone.id].tapped
    assert s.state.cards[forest.id].tapped and not s.state.cards[bear.id].tapped
    events=[e for e in s.state.rules.events if e.kind=='zone_change' and e.card in (clone.id,forest.id,bear.id) and e.to_zone=='p1:battlefield']
    assert len({e.batch for e in events[-3:]})==1
    roundtrip(s)


def test_surfer_external_spelunking_preserves_native_enter_untapped_override(cards):
    s=gameplay.gameplay.setup(cards,'Silver Surfer, Cosmic Voyager','Spelunking')
    put(s,'Spelunking','battlefield')
    land=put(s,'Forest','battlefield')
    surfer(s,[land.id])
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[land.id].zone=='p1:battlefield' and not s.state.cards[land.id].tapped
    roundtrip(s)


def test_surfer_original_trigger_can_retarget_new_source_incarnation_after_real_ephemerate(cards):
    from tests.test_rules_bandmate_references import mana

    s=gameplay.gameplay.setup(cards,'Silver Surfer, Cosmic Voyager','Ephemerate','Deflecting Swat')
    bear=put(s,'Grizzly Bears','battlefield')
    source=put(s,'Silver Surfer, Cosmic Voyager','hand')
    mana(s,U=2,C=4)
    act(s,'p1',type='cast_spell',card_id=source.id)
    while s.state.rules.decision is None:
        act(s,s.state.rules.priority,type='pass_priority')
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id])
    old=s.state.rules.object_id(source.id)
    original=next(k for k,e in s.state.rules.stack.items() if e.kind=='trigger' and e.source_object==old)
    cast(s,'Ephemerate',targets=[source.id])
    new=s.state.rules.object_id(source.id)
    assert new!=old
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
    newer=[k for k,e in s.state.rules.stack.items() if e.kind=='trigger' and e.source_object==new]
    while any(k in s.state.rules.stack for k in newer):
        act(s,s.state.rules.priority,type='pass_priority')
    assert original in s.state.rules.stack
    cast(s,'Deflecting Swat',targets=[original])
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='choose_new_targets'
    assert source.id in [o.id for o in d.options]
    answer(s,[source.id])
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    roundtrip(s)


def test_surfer_real_flash_zero_target_then_flying_blocks_ground_creature(cards):
    from app.game.errors import ActionError

    s=gameplay.gameplay.setup(cards,'Silver Surfer, Cosmic Voyager')
    blocker=put(s,'Grizzly Bears','battlefield',pid='p2')
    to_phase(s,'main1',turn=2)
    act(s,'p2',type='pass_priority')
    act(s,'p3',type='pass_priority')
    source=surfer(s,[])
    assert not s.state.rules.delayed
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    to_phase(s,'declare_blockers',turn=4)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':blocker.id,'attacker_id':source.id}])
    assert s.state.model_dump_json()==before
    act(s,'p2',type='declare_blockers',blocks=[])
    to_phase(s,'main2',turn=4)
    assert s.state.players['p2'].life==35
    roundtrip(s)


@pytest.mark.parametrize('all_illegal',[False,True])
def test_surfer_native_partial_or_all_illegal_targets_do_not_follow_dead_objects(cards,all_illegal):
    from tests.test_rules_bandmate_references import mana

    s=gameplay.gameplay.setup(cards,'Silver Surfer, Cosmic Voyager','Murder')
    bear=put(s,'Grizzly Bears','battlefield')
    land=put(s,'Forest','battlefield')
    source=put(s,'Silver Surfer, Cosmic Voyager','hand')
    mana(s,U=2,C=4)
    act(s,'p1',type='cast_spell',card_id=source.id)
    while s.state.rules.decision is None:
        act(s,s.state.rules.priority,type='pass_priority')
    d=s.state.rules.decision
    assert source.id not in [o.id for o in d.options]
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id] if all_illegal else [bear.id,land.id])
    cast(s,'Murder',targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:graveyard'
    assert s.state.cards[land.id].zone==('p1:battlefield' if all_illegal else 'p1:exile')
    assert bool(s.state.rules.delayed)!=all_illegal
    roundtrip(s)


def test_surfer_returned_spelunking_is_not_a_preexisting_entry_modifier(cards):
    s=gameplay.gameplay.setup(cards,'Silver Surfer, Cosmic Voyager','Spelunking')
    enchantment=put(s,'Spelunking','battlefield')
    land=put(s,'Forest','battlefield')
    surfer(s,[land.id,enchantment.id])
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[land.id].zone=='p1:battlefield' and s.state.cards[land.id].tapped
    roundtrip(s)


def test_surfer_later_exile_incarnation_does_not_return(cards):
    s=gameplay.gameplay.setup(cards,'Silver Surfer, Cosmic Voyager')
    land=put(s,'Forest','battlefield')
    surfer(s,[land.id])
    act(s,'p1',type='move',card_ids=[land.id],to={'zone':'hand','player':'p1'})
    act(s,'p1',type='move',card_ids=[land.id],to={'zone':'exile','player':'p1'})
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[land.id].zone=='p1:exile'
    roundtrip(s)


def test_surfer_genuine_cold_copy_entry_retains_land_tapped_flag_and_simultaneous_returns(cards,tmp_path):
    s=gameplay.gameplay.setup(cards,'Silver Surfer, Cosmic Voyager','Clone','Dryad Arbor')
    bear=put(s,'Grizzly Bears','battlefield')
    arbor=put(s,'Dryad Arbor','battlefield')
    forest=put(s,'Forest','battlefield')
    clone=cast(s,'Clone')
    answer(s,[bear.id])
    surfer(s,[clone.id,forest.id,bear.id])
    to_phase(s,'end',turn=1)
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    assert all(s.state.cards[cid].zone.endswith(':exile') for cid in (clone.id,forest.id,bear.id))
    s=stage_fresh(s,cards,tmp_path/'copy.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[arbor.id]})
    assert s.state.cards[clone.id].zone=='p1:battlefield' and s.state.cards[clone.id].tapped
    assert s.state.cards[forest.id].tapped and not s.state.cards[bear.id].tapped
    events=[e for e in s.state.rules.events if e.kind=='zone_change' and e.card in (clone.id,forest.id,bear.id) and e.to_zone=='p1:battlefield']
    assert len({e.batch for e in events[-3:]})==1
    roundtrip(s)


def test_surfer_whole_canonical_coverage(cards):
    from app.rules import coverage

    result=coverage.of_card_data(cards.resolve('Silver Surfer, Cosmic Voyager'))
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
    result=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),actor,json.dumps(payload)],cwd=Path(replacements.__file__).resolve().parents[2],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    return GameSession(GameState.model_validate_json(path.read_text()),cards=cards)
