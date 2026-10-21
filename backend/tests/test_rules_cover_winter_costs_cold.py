"""Genuine saved production cumulative-upkeep snow payment."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.game_helpers import act
from tests.test_rules_cover_winter_costs import cards as cards
from tests.test_rules_wave43c_keywords import lands, prompt
from tests.wave9c_kit import build, put


def test_fresh_process_real_two_snow_cumulative_payment(cards, tmp_path):
    s = build(cards, ['Cover of Winter', *(['Snow-Covered Forest'] * 2)])
    cover = put(s, 'Cover of Winter')
    snow = lands(s, 'Snow-Covered Forest', 2)
    act(s, 'p1', type='counter', card_ids=[cover.id], kind='age', delta=1)
    d = prompt(s, 'Cover of Winter')
    assert d.resume['step'] == 'pay_or_sacrifice' and s.state.cards[cover.id].counters.get('age') == 2
    save = tmp_path / 'cover.json'
    save.write_text(s.state.model_dump_json())
    code = r'''
import json,sys
from pathlib import Path
from app.rules import engine
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle
save,db,cover,snow=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
assert d.resume['cost']=='{S}{S}'
act(s,'p1',type='choose',decision_id=d.id,option_ids=['pay'])
settle(s)
assert s.state.cards[cover].zone=='p1:battlefield' and s.state.cards[cover].counters.get('age')==2
assert all(s.state.cards[c].tapped for c in json.loads(snow))
assert not s.state.players['p1'].mana and s.state.rules.decision is None
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(save), str(cards.db_path), cover.id, json.dumps(snow)],
                            capture_output=True, text=True, timeout=90, cwd=Path(__file__).parent.parent)
    assert result.returncode == 0, result.stdout + result.stderr
