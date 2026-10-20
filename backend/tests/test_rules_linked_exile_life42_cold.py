"""Production-only fresh-process linked-exile and nominal-life continuations."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests import test_rules_linked_exile_life42 as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_wave4h_activation_costs import ability

cards=gameplay.cards


def fresh(s,cards,path,actor,payload):
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
for _ in range(60):
 d=s.state.rules.decision
 if d is not None:
  if d.kind=='order' and d.resume.get('step')!='order_library':
   s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[o.id for o in d.options]})
  else:
   break
 elif s.state.zones.get('stack'):
  s.perform(s.state.rules.priority,{'type':'pass_priority'})
 else:
  break
path.write_text(s.state.model_dump_json())
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),actor,json.dumps(payload)],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    return GameSession(GameState.model_validate_json(path.read_text()),cards=cards)


@pytest.mark.parametrize('name',['Bronzebeak Foragers','Luminate Primordial'])
def test_actual_exact_linked_exile_and_nominal_life_continuation_after_fresh_process(cards,tmp_path,name):
    s=gameplay.setup(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    if name=='Bronzebeak Foragers':
        source=gameplay.enter(s,name,[bear.id])
        act(s,'p1',type='set_prefs',hold_priority=True)
        mana(s,C=2,W=1)
        act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{X}'),x_value=2,targets=[bear.id])
        payload={'type':'pass_priority'}
        actor=s.state.rules.priority
    else:
        source=put(s,name,'hand')
        mana(s,C=5,W=2)
        act(s,'p1',type='cast_spell',card_id=source.id)
        settle(s)
        d=s.state.rules.decision
        payload={'type':'choose','decision_id':d.id,'option_ids':[next(o.id for o in d.options if o.card_id==bear.id)]}
        actor=d.decider or d.player
    s=fresh(s,cards,tmp_path/'linked42.json',actor,payload)
    assert s.state.rules.decision is None
    if name=='Bronzebeak Foragers':
        assert s.state.cards[bear.id].zone=='p2:graveyard' and s.state.players['p1'].life==42
    else:
        assert s.state.cards[bear.id].zone=='p2:exile' and s.state.players['p2'].life==42
    # The child result has no shared action history; persistence is tested independently.
    assert s.state.model_validate_json(s.state.model_dump_json())==s.state
