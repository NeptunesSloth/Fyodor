"""shapes.py IN OUT: re-measure single blockers at the `app` on sys.path; cluster the non-FULL ones' blocking lines by a normalized shape."""
import json, re, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from app.rules import coverage
from tools.commander_coverage import rows
src = json.load(open(sys.argv[1])); names = {c["name"] for c in src}
data, _ = rows(Path("/home/user/Fyodor/data/cards.sqlite"))
lvl = {d["name"]: coverage.of_card_data(d).level for d in data if d["name"] in names}
left = [c for c in src if lvl.get(c["name"]) != "FULL"]
COL = r"\b(white|blue|black|red|green|colorless|multicolored|monocolored)\b"
def shape(t, name):
    t = t.replace(name, "~").replace(name.split(",")[0], "~")
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"\{[^}]+\}", "{M}", t); t = re.sub(r"\b(\d+|X|one|two|three|four|five)\b", "N", t)
    t = re.sub(r"[+-]N/[+-]N", "±P/T", t); t = re.sub(COL, "COLOR", t, flags=re.I)
    return t.strip().lower()
cl = defaultdict(list)
for c in left: cl[shape(c["text"], c["name"])].append(c["name"])
out = sorted(cl.items(), key=lambda kv: -len(kv[1]))
json.dump([{"shape": k, "n": len(v), "cards": v} for k, v in out], open(sys.argv[2], "w"), indent=0)
print(len(src), "->", len(left), "clusters", len(out), "size>=2:", sum(1 for k, v in out if len(v) > 1), "cards in them:", sum(len(v) for k, v in out if len(v) > 1))
for k, v in out[:40]: print(len(v), k[:150])
