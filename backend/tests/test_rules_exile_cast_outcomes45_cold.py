"""Unadmitted cold research only; admitted native proofs use production_cold."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase

cards=gameplay.cards


def fresh(s,cards,path,actor,payload):
    from app.game.session import GameSession
    from app.game.state import GameState

    path.write_text(s.state.model_dump_json())
    code='''
import json,sys
from pathlib import Path

import pytest
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
                          cwd=Path(gameplay.engine.__file__).resolve().parents[2],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    return GameSession(GameState.model_validate_json(path.read_text()),cards=cards)


def test_anrakyr_cold_attack_to_artifact_life_alternative_payment(cards,tmp_path):
    s=gameplay.setup(cards,'Anrakyr the Traveller')
    source=put(s,'Anrakyr the Traveller','battlefield')
    altar=put(s,"Ashnod's Altar",'graveyard')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    d=s.state.rules.decision
    life=s.state.players['p1'].life
    s=fresh(s,cards,tmp_path/'life.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[altar.id]})
    assert s.state.players['p1'].life==life-3
    assert s.state.cards[altar.id].zone=='p1:battlefield'
