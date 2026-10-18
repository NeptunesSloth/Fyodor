"""cmdr_left_now.py IN OUT: re-measure a cmdrs_left list at the `app` on sys.path; keep the non-FULL ones."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from app.rules import coverage
from tools.commander_coverage import rows
src = json.load(open(sys.argv[1])); names = {c["name"] for c in src}
data, _ = rows(Path("/home/user/Fyodor/data/cards.sqlite"))
lvl = {d["name"]: coverage.of_card_data(d).level for d in data if d["name"] in names}
left = [c for c in src if lvl.get(c["name"]) != "FULL"]
json.dump(left, open(sys.argv[2], "w"), indent=0)
from collections import Counter
print(len(src), "->", len(left), Counter(min(len(c["lines"]), 3) for c in left))
