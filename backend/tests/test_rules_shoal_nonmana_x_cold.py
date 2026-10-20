"""Genuine fresh processes at native private-payment and source-choice pauses."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_rules_designations import put, settle
from tests.test_rules_shoal_nonmana_x import begin, game
from tests.test_rules_shoal_nonmana_x import cards as cards


@pytest.mark.parametrize('pause', ['cost', 'source'])
def test_fresh_process_production_native_shoal_cost_and_source(cards, tmp_path, pause):
    s = game(cards)
    source = put(s, 'Pestilence', 'battlefield', 'p2')
    white = put(s, "Acolyte's Reward" if pause == 'cost' else 'Selfless Squire', 'hand')
    if pause == 'cost':
        put(s, 'Samite Ministration', 'hand')
    shoal = begin(s, 2 if pause == 'cost' else 4)
    if pause == 'source':
        settle(s)
        assert s.state.rules.decision.resume['step'] == 'prevention_frontier_source'
    else:
        assert s.state.rules.decision.resume['step'] == 'ability_cost'
    save = tmp_path / 'shoal.json'
    save.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.rules import engine
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle
save,db,pause,white,shoal,source=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
if pause=='cost':
 d=s.state.rules.decision
 act(s,'p1',type='choose',decision_id=d.id,option_ids=[white])
 receipt=s.state.rules.payments[s.state.rules.object_id(shoal)]
 assert receipt.x==2 and receipt.exiled==[white] and not receipt.mana_spent
 settle(s)
d=s.state.rules.decision
assert d.resume['step']=='prevention_frontier_source'
option=next(o.id for o in d.options if o.card_id==source)
act(s,'p1',type='choose',decision_id=d.id,option_ids=[option])
settle(s)
record=next(r for r in s.state.rules.replacements if r['source_card']==shoal)
assert record['op']['do']=='redirect' and record['op']['allocate']
assert record['op']['limit']==(2 if pause=='cost' else 4)
assert record['op']['pid']=='p2' and not record['op'].get('once')
assert record['match']['source']['oids']==[s.state.rules.object_id(source)]
assert s.state.cards[white].zone=='p1:exile' and s.state.cards[shoal].zone=='p1:graveyard'
assert s.state.rules.decision is None
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(save), str(cards.db_path), pause, white.id, shoal.id, source.id],
                            capture_output=True, text=True, timeout=90, cwd=Path(__file__).parent.parent)
    assert result.returncode == 0, result.stdout + result.stderr
