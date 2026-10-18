"""cardq: python cardq.py REGEX [--level FULL|PARTIAL] [--defs] [--limit N] [--grep-def SUBSTR]
Search Commander-legal cards by Oracle text regex; print level and (optionally) parsed definitions."""
import argparse, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from app.rules import commander, coverage
from app.rules import scripts as templates
from tools.commander_coverage import rows
from tools.inventory import _faces

ap = argparse.ArgumentParser()
ap.add_argument("rx"); ap.add_argument("--level"); ap.add_argument("--defs", action="store_true")
ap.add_argument("--limit", type=int, default=20); ap.add_argument("--grep-def")
a = ap.parse_args()
rx = re.compile(a.rx, re.I | re.S)
data, _ = rows(Path("../data/cards.sqlite"))
data.sort(key=lambda d: int(d.get("edhrec_rank") or 10**9))
n = 0
for d in data:
    text = d.get("oracle_text") or " // ".join(f.get("oracle_text", "") for f in d["faces"])
    if not rx.search(text) or commander.legality(d) != "legal":
        continue
    lvl = coverage.of_card_data(d).level
    if a.level and lvl != a.level:
        continue
    defs_s = ""
    if a.defs or a.grep_def:
        out = []
        for ch in _faces(d):
            for k, v in templates.definitions(ch).items():
                out.append(f"  [{k}] {json.dumps(v.model_dump() if hasattr(v,'model_dump') else v, default=str)[:900]}")
        defs_s = "\n".join(out)
        if a.grep_def and a.grep_def not in defs_s:
            continue
    print(f"== {d['name']} [{lvl}] rank={d.get('edhrec_rank')}\n  {text!r}")
    if a.defs: print(defs_s)
    n += 1
    if n >= a.limit: break
