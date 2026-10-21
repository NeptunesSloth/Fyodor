"""True new-process resumes through opt-in native effect/combat/payment sites."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_rules_prevention_frontier_bridge import answer, earth_harm
from tests.test_rules_prevention_frontier_bridge import cards as cards
from tests.test_rules_prevention_frontier_bridge_sites import combat_pending, mana_pending


@pytest.mark.parametrize('stage', ['effect', 'mana', 'mana_rider', 'combat', 'combat_rider'])
def test_actual_joint_bridge_fresh_process_sites(cards, tmp_path, stage):
    if stage == 'effect':
        s, subject, _ = earth_harm(cards)
        subject, top = subject.id, ''
    else:
        s, subject, top = (mana_pending if stage.startswith('mana') else combat_pending)(cards)
        if stage.endswith('_rider'):
            answer(s, 1)
    saved = tmp_path / 'joint.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.rules import engine
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import prevention_frontier_bridge as bridge
from tests.game_helpers import act
from tests.test_rules_designations import settle, roundtrip
from tests.test_rules_prevention_frontier_bridge import answer
save,db,stage,subject,top=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
if stage=='effect':
 while s.state.rules.decision:
  answer(s,1)
 assert s.state.players['p1'].life==39 and s.state.cards[subject].damage==1
 assert s.state.players['p2'].life==38 and s.state.players['p3'].life==36
 assert not s.state.rules.stack and not s.state.rules.replacements
else:
 if not stage.endswith('_rider'):
  assert s.state.rules.decision.resume['step']==bridge.STEP
  answer(s,1)
 assert s.state.rules.decision.resume['step']!=bridge.STEP
 if stage.startswith('mana'):
  assert subject not in s.state.rules.stack
  assert s.state.rules.spells_this_turn('p1',s.state.turn.number)==0
 else:
  assert s.state.players['p1'].life==39 and s.state.table.monarch=='p1'
 d=s.state.rules.decision
 act(s,'p1',type='choose',decision_id=d.id,option_ids=['decline'])
 assert s.state.cards[top].zone=='p1:hand'
 if stage.startswith('mana'):
  assert s.state.cards[subject].zone=='stack'
  assert s.state.rules.spells_this_turn('p1',s.state.turn.number)==1
 settle(s)
 if stage.startswith('mana'):
  assert s.state.cards[subject].zone=='p1:battlefield'
  assert s.state.players['p1'].life==40
 else:
  assert s.state.players['p1'].life==39 and s.state.table.monarch=='p2'
 assert not s.state.rules.replacements
roundtrip(s)
settle(s)
assert s.state.rules.decision is None
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), stage, subject, top],
                            capture_output=True, text=True, timeout=90, cwd=Path(__file__).parent.parent)
    assert result.returncode == 0, result.stdout + result.stderr
