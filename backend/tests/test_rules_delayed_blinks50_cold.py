"""Fresh-process pending exact-object blink staging; no rules/payment mocks."""
import json
import subprocess
import sys
from pathlib import Path

from app.game.session import GameSession
from app.game.state import GameState
from tests import test_rules_delayed_blinks50 as gameplay
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

cards=gameplay.cards


def fresh(s,cards,path,actor,payload):
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


def test_yorion_cold_resolution_choice_then_cold_actual_delayed_return(cards,tmp_path):
    s=gameplay.gameplay.setup(cards,'Yorion, Sky Nomad')
    own=put(s,'Grizzly Bears','battlefield')
    cast(s,'Yorion, Sky Nomad')
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'choice.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[own.id]})
    assert s.state.cards[own.id].zone=='p1:exile'
    to_phase(s,'end',turn=1)
    s=fresh(s,cards,tmp_path/'return.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.cards[own.id].zone=='p1:battlefield'
    roundtrip(s)


def test_nahiri_cold_delayed_return_after_source_departure(cards,tmp_path):
    from tests.test_rules_library_look import settle

    s=gameplay.gameplay.setup(cards,"Nahiri's Resolve")
    source=put(s,"Nahiri's Resolve",'battlefield')
    own=put(s,'Grizzly Bears','battlefield')
    to_phase(s,'end',turn=1)
    settle(s)
    answer(s,[own.id])
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'graveyard','player':'p1'})
    to_phase(s,'upkeep',turn=4)
    s=fresh(s,cards,tmp_path/'return.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.cards[own.id].zone=='p1:battlefield'
    roundtrip(s)
