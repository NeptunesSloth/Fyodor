"""Cold completed-source B records need only the production planner and riders."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_rules_designations import put
from tests.test_rules_prevention_frontier_bridge import cards as cards
from tests.test_rules_prevention_frontier_bridge import game
from tests.test_rules_prevention_outcomes import cast, source_choice
from tests.test_rules_wave30m_durations import to_phase


@pytest.mark.parametrize('name', ["Harm's Way", 'Shining Shoal', 'Divine Deflection', 'Refraction Trap'])
def test_full_card_actual_simultaneous_damage_resume_without_any_child_adapter(cards, tmp_path, name):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=2)
    quake = cast(s, 'Earthquake', pid='p2', x_value=2, resolve=False)
    cast(s, name, ['p3'], **({'x_value': 2} if name in ('Shining Shoal', 'Divine Deflection') else {}))
    if name != 'Divine Deflection':
        source_choice(s, quake)
    saved = tmp_path / 'full-card.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys,json
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import prevention_frontier_journal as journal
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
save,db,name,bear=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
while s.state.rules.decision:
 d=s.state.rules.decision
 q=journal.question(Plan(s.state,d.player,repo,None),journal.Frame.loads(d.resume['frame']))
 amount=2 if name=='Refraction Trap' and json.loads(q.key)[2]==bear else 1
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[],name=str(amount))
 settle(s)
assert s.state.players['p1'].life==39 and s.state.players['p2'].life==38
assert s.state.players['p3'].life==(35 if name=='Refraction Trap' else 36)
assert s.state.cards[bear].damage==(0 if name=='Refraction Trap' else 1)
assert not s.state.rules.replacements and not s.state.rules.stack
roundtrip(s)
settle(s)
assert s.state.rules.decision is None
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name, bear.id],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cover_actual_static_age_budget_cold_resume_without_definition_or_candidate_adapter(cards, tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_damage_redirection import attack, damage
    s = game(cards)
    cover = put(s, 'Cover of Winter', 'battlefield')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[cover.id], kind='age', delta=1)
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    saved = tmp_path / 'cover.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
save,db,cover=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
assert d.resume['step']=='joint_prevention_question'
act(s,d.player,type='choose',decision_id=d.id,option_ids=[],name='1')
settle(s)
assert s.state.players['p1'].life==39 and s.state.cards[cover].counters['age']==1
assert not s.state.rules.prevention and not s.state.rules.decision
roundtrip(s)
settle(s)
assert s.state.players['p1'].life==39
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), cover.id],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_two_controller_redirect_cycle_cold_partial_interior_vector(cards, tmp_path):
    from tests.test_rules_prevention_frontier_bridge import answer
    from tests.test_rules_prevention_frontier_full_cards import cycle_pending
    s = cycle_pending(cards)
    answer(s, 1)
    answer(s, 1)
    saved = tmp_path / 'cycle.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
save,db=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
for _ in range(2):
 d=s.state.rules.decision
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[],name='1')
 settle(s)
assert s.state.rules.decision is None and not s.state.rules.replacements
assert all(s.state.players[p].life==38 for p in ('p1','p2','p3'))
assert not s.state.rules.stack
roundtrip(s)
settle(s)
assert all(s.state.players[p].life==38 for p in ('p1','p2','p3'))
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
