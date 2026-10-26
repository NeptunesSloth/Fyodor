"""defprobe.py "Card" ["old" "new"]...: print scripts.define of each ability (text edited)."""
import sys, json
from pathlib import Path
from tools.commander_coverage import rows
from app.rules import scripts, oracle
from app.rules.characteristics import printed_from_data
name, *pairs = sys.argv[1:]
d = next(d for d in rows(Path("/home/user/Fyodor/data/cards.sqlite"))[0] if d["name"] == name)
t = d["oracle_text"]
for o, n in zip(pairs[::2], pairs[1::2]):
    assert o in t, o
    t = t.replace(o, n)
ch = printed_from_data({**d, "oracle_text": t}, 0)
for ab in ch.abilities:
    print(ab.index, ab.kind, ab.text[:90]); print("   ", json.dumps(scripts.define(ab, ch), default=str)[:900])
