"""Unimported Obzedat using native exile, delayed receipts and permanent haste."""
import pytest

from tests import test_rules_delayed_blinks50 as gameplay
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

cards=gameplay.cards




def test_obzedat_real_etb_optional_exile_owner_return_and_permanent_haste_after_control_change(cards):
    s=gameplay.gameplay.setup(cards,'Obzedat, Ghost Council')
    cast(s,'Obzedat, Ghost Council')
    answer(s,['p2'])
    source=next(c for c in s.state.cards.values() if c.name=='Obzedat, Ghost Council' and c.zone=='p1:battlefield')
    assert s.state.players['p1'].life==42 and s.state.players['p2'].life==38
    to_phase(s,'end',turn=1)
    settle(s)
    answer(s,['yes'])
    assert s.state.cards[source.id].zone=='p1:exile'
    to_phase(s,'upkeep',turn=4)
    settle(s)
    answer(s,['p2'])
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert s.state.players['p1'].life==44 and s.state.players['p2'].life==36
    to_phase(s,'end',turn=4)
    settle(s)
    answer(s,['no'])
    to_phase(s,'main1',turn=5)
    act(s,'p2',type='set_controller',card_ids=[source.id],player='p2')
    to_phase(s,'declare_attackers',turn=5)
    act(s,'p2',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p1'}])
    to_phase(s,'main2',turn=5)
    assert s.state.players['p1'].life==39
    roundtrip(s)


def test_obzedat_foreign_controller_delayed_upkeep_is_not_owners_upkeep(cards):
    s=gameplay.gameplay.setup(cards,'Obzedat, Ghost Council')
    cast(s,'Obzedat, Ghost Council')
    answer(s,['p2'])
    source=next(c for c in s.state.cards.values() if c.name=='Obzedat, Ghost Council' and c.zone=='p1:battlefield')
    to_phase(s,'end',turn=1)
    settle(s)
    answer(s,['no'])
    to_phase(s,'main1',turn=2)
    act(s,'p2',type='set_controller',card_ids=[source.id],player='p2')
    to_phase(s,'end',turn=2)
    settle(s)
    assert s.state.rules.decision.player=='p2'
    answer(s,['yes'])
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:exile'
    to_phase(s,'upkeep',turn=5)
    settle(s)
    assert s.state.rules.decision.player=='p1'
    answer(s,['p2'])
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert s.state.cards[source.id].controller=='p1'
    roundtrip(s)


def test_obzedat_old_exile_incarnation_cannot_return(cards):
    s=gameplay.gameplay.setup(cards,'Obzedat, Ghost Council')
    cast(s,'Obzedat, Ghost Council')
    answer(s,['p2'])
    source=next(c for c in s.state.cards.values() if c.name=='Obzedat, Ghost Council' and c.zone=='p1:battlefield')
    to_phase(s,'end',turn=1)
    settle(s)
    answer(s,['yes'])
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'hand','player':'p1'})
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'exile','player':'p1'})
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_obzedat_permanent_haste_does_not_follow_new_battlefield_incarnation(cards):
    from app.game.errors import ActionError

    s=gameplay.gameplay.setup(cards,'Obzedat, Ghost Council')
    cast(s,'Obzedat, Ghost Council')
    answer(s,['p2'])
    source=next(c for c in s.state.cards.values() if c.name=='Obzedat, Ghost Council' and c.zone=='p1:battlefield')
    to_phase(s,'end',turn=1)
    settle(s)
    answer(s,['yes'])
    to_phase(s,'upkeep',turn=4)
    settle(s)
    answer(s,['p2'])
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'hand','player':'p1'})
    cast(s,'Obzedat, Ghost Council')
    answer(s,['p2'])
    to_phase(s,'declare_attackers',turn=4)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p3'}])
    assert s.state.model_dump_json()==before
    roundtrip(s)


def test_obzedat_genuine_cold_delayed_return_then_real_haste_attack(cards,tmp_path):
    s=gameplay.gameplay.setup(cards,'Obzedat, Ghost Council')
    cast(s,'Obzedat, Ghost Council')
    answer(s,['p2'])
    source=next(c for c in s.state.cards.values() if c.name=='Obzedat, Ghost Council' and c.zone=='p1:battlefield')
    to_phase(s,'end',turn=1)
    settle(s)
    answer(s,['yes'])
    to_phase(s,'upkeep',turn=4)
    s=stage_fresh(s,cards,tmp_path/'return.json',s.state.rules.priority,{'type':'pass_priority'})
    answer(s,['p2'])
    assert s.state.cards[source.id].zone=='p1:battlefield'
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p3'}])
    to_phase(s,'main2',turn=4)
    assert s.state.players['p3'].life==35
    roundtrip(s)


def test_obzedat_whole_canonical_coverage(cards):
    from app.rules import coverage

    result=coverage.of_card_data(cards.resolve('Obzedat, Ghost Council'))
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
repo=CardRepository(Path(sys.argv[2]),ImageStore(path.parent/'cold-images'))
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
