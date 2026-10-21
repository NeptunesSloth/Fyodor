"""Fresh-process JSON prefix proof; no production chooser or bridge admission."""
from __future__ import annotations

import subprocess
import sys

from app.rules import prevention_frontier_discovery as lazy
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_prevention_frontier_grounding import setup


def test_fresh_process_pending_order_separate_allocation_and_joint_native_ground(cards, tmp_path):
    plan, frame, events = setup(cards)
    a, b = (p.id for p in frame.pools)
    draft = lazy.choose_order(plan, lazy.start(plan, events), 'left', a, 'p1')
    state = tmp_path / 'state.json'
    saved = tmp_path / 'frontier.json'
    state.write_text(plan.state.model_dump_json())
    saved.write_text(draft.dumps())
    code = r'''
import sys
from pathlib import Path
from app.rules import engine
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.rules.plan import Plan
from app.rules import prevention_frontier_discovery as lazy
from app.rules import prevention_frontier_joint_draft as joint
state,saved,db,a,b=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
plan=Plan(GameState.model_validate_json(Path(state).read_text()),'p3',repo,None)
before=plan.state.model_dump_json()
draft=lazy.Draft.loads(Path(saved).read_text())
assert draft.pending.order_player=='p1' and draft.pending.allocation_player=='p3'
draft=lazy.choose_amount(plan,draft,1,'p3')
for leaf,candidate,order_player,owner,n in [('right',b,'p2','p2',1),('left',b,'p1','p2',2),('right',a,'p2','p3',2)]:
 draft=lazy.choose_order(plan,draft,leaf,candidate,order_player)
 draft=lazy.Draft.loads(draft.dumps())
 draft=lazy.choose_amount(plan,draft,n,owner)
result=joint.complete(plan,draft,batch='fresh-native-prefix')
assert [e['amount'] for e in result.grounded.events]==[1,1]
assert sum(r['amount'] for r in result.grounded.receipts)==6
assert plan.state.model_dump_json()==before
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(state), str(saved), str(cards.db_path), a, b],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
