"""levels.py --out FILE [-j N] [--db PATH]: {name: [level, commander, defs_hash]} for every Commander-legal card, measured from the
`app` on sys.path (run with PYTHONPATH=<worktree>/backend). defs_hash: a hash of the parsed definitions of every face (detects changed parses)."""
import argparse, hashlib, json, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import app
from app.rules import commander, coverage
from app.rules import scripts as templates
from tools.commander_coverage import rows
from tools.inventory import _faces


def one(d):
    if commander.legality(d) != "legal":
        return None
    lvl = coverage.of_card_data(d).level
    blob = []
    for ch in _faces(d):
        for k, v in sorted(templates.definitions(ch).items()):
            blob.append(f"{k}:{json.dumps(v.model_dump() if hasattr(v, 'model_dump') else v, default=str, sort_keys=True)}")
    return d["name"], [lvl, bool(commander.can_be_commander(d)), hashlib.blake2b("\n".join(blob).encode(), digest_size=8).hexdigest()]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("-j", type=int, default=2)
    ap.add_argument("--db", default="/home/user/Fyodor/data/cards.sqlite")
    a = ap.parse_args()
    print("measuring", app.__file__, file=sys.stderr)
    data, _ = rows(Path(a.db))
    with ProcessPoolExecutor(a.j) as ex:
        out = dict(x for x in ex.map(one, data, chunksize=200) if x)
    Path(a.out).write_text(json.dumps(out, sort_keys=True))
    full = sum(v[0] == "FULL" for v in out.values())
    print(f"cards {len(out)} FULL {full} ({100*full/len(out):.1f}%) commanders FULL {sum(v[0]=='FULL' and v[1] for v in out.values())}")
