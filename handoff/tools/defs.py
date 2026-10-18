"""defs.py NAME... : the parsed definitions of every face (JSON, sorted keys), one card per block (run via w30j.sh / w30j_base.sh)."""
import json, sqlite3, sys
from app.rules import scripts as templates
from tools.inventory import _faces
from tools.commander_coverage import rows

db = sqlite3.connect("file:/home/user/Fyodor/data/cards.sqlite?mode=ro", uri=True)
names = set(sys.argv[1:])
data, _ = rows(__import__("pathlib").Path("/home/user/Fyodor/data/cards.sqlite"))
for d in data:
    if d["name"] in names:
        print("##", d["name"])
        for ch in _faces(d):
            for k, v in sorted(templates.definitions(ch).items()):
                print(k, json.dumps(v.model_dump() if hasattr(v, "model_dump") else v, default=str, sort_keys=True))
