"""defs_of.py "Name": print scripts.definitions for a card from data/cards.sqlite, using the `app` in the cwd."""
import json, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from app.rules import scripts
from tools.commander_coverage import rows
from tools.inventory import _faces
data, _ = rows(Path("/home/user/Fyodor/data/cards.sqlite"))
d = next(d for d in data if d["name"] == sys.argv[1])
for ch in _faces(d):
    for k, v in sorted(scripts.definitions(ch).items()):
        print(k, json.dumps(v.model_dump() if hasattr(v, "model_dump") else v, default=str, sort_keys=True)[:1500])
