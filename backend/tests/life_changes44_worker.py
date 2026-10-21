import sys
from pathlib import Path

from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState

statefile, db, option = sys.argv[1:]
r = CardRepository(Path(db), ImageStore(Path("/tmp/fyodor-life44-cold-images")))
s = GameSession(GameState.model_validate_json(Path(statefile).read_text()), cards=r)
d = s.state.rules.decision
assert d.resume["site"] == "life_changes44"
s.perform(d.player, {"type": "choose", "decision_id": d.id, "option_ids": [option]})
for _ in range(40):
    d = s.state.rules.decision
    if d and d.kind == "order":
        s.perform(d.player, {"type": "choose", "decision_id": d.id, "option_ids": [o.id for o in d.options]})
    elif d is None and s.state.zones.get("stack"):
        s.perform(s.state.rules.priority, {"type": "pass_priority"})
    else:
        break
assert s.state.rules.decision is None
Path(statefile).write_text(s.state.model_dump_json())
