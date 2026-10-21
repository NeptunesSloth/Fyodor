"""Fresh-process native choice restoration; no prototype or parser registration."""
import json
import subprocess
import sys


def cold_choose(s, cards, tmp_path, ids, *, name=None):
    from app.game.session import GameSession
    from app.game.state import GameState

    original, restored = tmp_path / 'original.json', tmp_path / 'restored.json'
    original.write_text(s.state.model_dump_json())
    code = '''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
repo=CardRepository(Path(sys.argv[1]),ImageStore(Path(sys.argv[2])))
s=GameSession(GameState.model_validate_json(Path(sys.argv[3]).read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':json.loads(sys.argv[5]),'name':json.loads(sys.argv[6])})
Path(sys.argv[4]).write_text(s.state.model_dump_json())
'''
    result = subprocess.run([sys.executable, '-c', code, str(cards.db_path), str(tmp_path / 'images'),
                             str(original), str(restored), json.dumps(ids), json.dumps(name)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return GameSession(GameState.model_validate_json(restored.read_text()), cards=cards)
