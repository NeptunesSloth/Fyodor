"""Fresh-process Spinneret staging; only exact leaf callbacks are registered."""
import json
import subprocess
import sys
from pathlib import Path

from app.game.session import GameSession
from app.game.state import GameState
from tests import test_rules_spinneret_damage49 as gameplay
from tests.test_rules_designations import put, roundtrip

pytestmark=gameplay.pytestmark
cards=gameplay.cards
staged=gameplay.staged


def fresh(s,cards,path,actor,payload):
    path.write_text(s.state.model_dump_json())
    code='''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import scripts,effects,engine
from app.rules import exile_damage_choices49 as leaf
native=scripts.define
scripts.define=lambda ability,ch:leaf.definition(ability,ch) or native(ability,ch)
scripts._cached.cache_clear()
path=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(path.parent/'images'))
s=GameSession(GameState.model_validate_json(path.read_text()),cards=repo)
s.perform(sys.argv[3],json.loads(sys.argv[4]))
while s.state.rules.decision is None and s.state.zones.get('stack'):
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
path.write_text(s.state.model_dump_json())
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),actor,json.dumps(payload)],
        cwd=Path(gameplay.scripts.__file__).resolve().parents[2],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    return GameSession(GameState.model_validate_json(path.read_text()),cards=cards)




def test_spinneret_cold_simultaneous_damage_threshold_then_exact_land_play(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana

    s=gameplay.gameplay.setup(cards,'Spinneret and Spiderling',"Chandra's Ignition",'Forest')
    source=put(s,'Spinneret and Spiderling','battlefield')
    act(s,'p1',type='counter',card_ids=[source.id],kind='+1/+1',delta=1)
    top=put(s,'Forest','library')
    spell=put(s,"Chandra's Ignition",'hand')
    mana(s,R=2,C=3)
    s=fresh(s,cards,tmp_path/'damage.json','p1',{'type':'cast_spell','card_id':spell.id,'targets':[source.id]})
    assert s.state.players['p2'].life==38 and s.state.players['p3'].life==38
    assert s.state.cards[top.id].zone=='p1:exile'
    assert len(s.state.rules.permissions)==1
    s=fresh(s,cards,tmp_path/'land.json','p1',{'type':'play_land','card_id':top.id})
    assert s.state.cards[top.id].zone=='p1:battlefield'
    roundtrip(s)
